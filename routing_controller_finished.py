# The program implements a simple controller for a network with 6 hosts and 5 switches.
# The switches are connected in a diamond topology (without vertical links):
#    - 3 hosts are connected to the left (s1) and 3 to the right (s5) edge of the diamond.
# Overall operation of the controller:
#    - default routing is set in all switches on the reception of packet_in messages form the switch,
#    - then the routing for (h1-h4) pair in switch s1 is changed every one second in a round-robin manner to load balance the traffic through switches s3, s4, s2.
import thread
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import Event, EventMixin
from pox.lib.util import dpidToStr
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.packet.arp import arp
from pox.lib.packet.ethernet import ethernet, ETHER_BROADCAST
from pox.lib.packet.packet_base import packet_base
from pox.lib.packet.packet_utils import *
import pox.lib.packet as pkt
from pox.lib.recoco import Timer
import time
import struct
import sys
import os
#### delay variables
start_time = 0.0
sent_time1=0.0
sent_time2=0.0
received_time1 = 0.0
received_time2 = 0.0
s1s2_src=0
s1s3_src=0
s1s4_src=0
s1s2_dst=0
s1s3_dst=0
s1s4_dst=0
src_dpid=0
dst_dpid=0
mytimer = None
OWD1=0.0
OWD2=0.0
delay=0


### apropos Intentu
active_intent_flows=[] ### aktywne flowy
class Intent(object):
        def __init__(self,h1,h2,demand):
                self.h1=h1
                self.h2=h2
                self.demand=demand
        def __eq__(self, other):
                if (isinstance(other, Intent)):
                        return self.h1 == other.h1 and self.h2 == other.h2 and self.demand == other.demand
                return False

class GetIntent(Event):
        def __init__(self,intent):
                Event.__init__(self)
                self.intent=intent

class EventHandler(EventMixin):
        _eventMixin_events = set([
    GetIntent
  ])

class Flow(object):
        def __init__(self,intent,timeout,pair_switch):
                self.intent=intent
                self.pair_switch=pair_switch
                self.timeout=timeout # timeout w sekundach
                self.start_time=time.time()
        def __eq__(self, other):
                if (isinstance(other, Flow)):
                        return self.intent == other.intent and self.pair_switch == other.pair_switch
                return False
#### handler GetIntent
s1s2_flows=[] ## obiekty klasy Flow z s1s2
s1s3_flows=[]
s1s4_flows=[]
### for testing purposes
intents=[Intent('10.0.0.1','10.0.0.4',50), Intent('10.0.0.1','10.0.0.5',200)]
def delete_flow_from_switch(intent):
	global s1_dpid
        msg=of.ofp_flow_mod()
        msg.command=of.OFPFC_DELETE
        msg.match.dl_type=0x0800
        msg.match.nw_dst=intent.h2
        core.openflow.getConnection(s1_dpid).send(msg)
	print "Deleted flow from switch"

def remove_from_lists(flow):
        global s1s2_flows,s1s3_flows,s1s4_flows
        if flow.pair_switch == 's1s2':
                for f in s1s2_flows:
                        if f == flow:
                                s1s2_flows.remove(f)
        elif flow.pair_switch == 's1s3':
                for f in s1s3_flows:
                        if f==flow:
                                s1s3_flows.remove(f)
        elif flow.pair_switch == 's1s4':
                for f in s1s4_flows:
                        if f== flow:
                                s1s4_flows.remove(f)


def handle_intent (intent, possible_flows,no_flows): ###ta funkcja ma na celu umieszczenie/zmodyfikowanie aktywny flowow bo nowy intent
# sie pojawil ktory wiemy ktorym laczem zestawic-> robi tez shuffle reszty flowow
        global active_intent_flows
        ### sprawdz czy intent nie jest taki sam tylko demand inny
        for flow in active_intent_flows:
                if intent.h1==flow.intent.h1 and intent.h2==flow.intent.h2:
                        if intent.demand < flow.intent.demand: ## jezeli wymagane jest nagle mniejsze opoznienie to trzeba zmienic
                                if flow.intent.pair_switch not in possible_flows: ##jezeli istniejacy flow nie jest
## w zidentyfikowany mozliwych flowach to trzeba wybrac ktorys z possible_flows (to lacze gdzie jest mniej flowow)
                                        minimum_no_flows=min(no_flows)
                                        index_min_flows=no_flows.index(minimum_no_flows)
                                        active_intent_flows.remove(flow) ## usun ten flow
                                        ## usun ich z s1s2_flows itd
                                        remove_from_lists(flow)
					delete_flow_from_switch(flow.intent)
                                        new_flow=Flow(intent,180,"") ## zastap go nowym
                                        if index_min_flows==0:
                                                new_flow.pair_switch='s1s2'
                                                s1s2_flows.append(new_flow)
                                        elif index_min_flows==1:
                                                new_flow.pair_switch='s1s3'
                                                s1s3_flows.append(new_flow)
                                        else:
                                                new_flow.pair_switch='s1s4'
                                                s1s4_flows.append(new_flow)
                                        active_intent_flows.append(new_flow)
					#send_info_to_switch(new_flow,flow.intent)
                                        return new_flow
                        else:
                                return None
        minimum_no_flows=min(no_flows)
        index_min_flows=no_flows.index(minimum_no_flows)
        new_flow=Flow(intent,180,"")
        if index_min_flows==0:
            new_flow.pair_switch='s1s2'
            s1s2_flows.append(new_flow)
        elif index_min_flows==1:
            new_flow.pair_switch='s1s3'
            s1s3_flows.append(new_flow)
        else:
            new_flow.pair_switch='s1s4'
            s1s4_flows.append(new_flow)
        active_intent_flows.append(new_flow)
        return new_flow

def send_info_to_switch(flow,intent):
	global s1_dpid
	msg = of.ofp_flow_mod()
        msg.command=of.OFPFC_MODIFY_STRICT
        msg.priority =100
        msg.idle_timeout = flow.timeout
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = intent.h2
        if flow.pair_switch=='s1s2':
            msg.actions.append(of.ofp_action_output(port = 4))
        elif flow.pair_switch=='s1s3':
            msg.actions.append(of.ofp_action_output(port = 5))
        else:
            msg.actions.append(of.ofp_action_output(port = 6))
	core.openflow.getConnection(s1_dpid).send(msg)

def _handler_GetIntent(event):
     global active_intent_flows,delay,s1_dpid,s1s2_src,s1s2_dst,s1s3_src,s1s3_dst,s1s4_src,s1s4_dst,src_dpid,dst_dpid
     ## measure s1s2
     src_dpid=s1s2_src
     dst_dpid=s1s2_dst
     delay=0
     if src_dpid<>0 and dst_dpid<>0:
        mytimer1=Timer(2, _timer_func, recurring=True)
     while delay ==0:
        continue
     mytimer1.cancel()
     s1s2_delay=delay
     print "s1s2 CALCULATED delay: ",delay
     delay=0
## measure s1s3
     src_dpid=s1s3_src
     dst_dpid=s1s3_dst
     if src_dpid<>0 and dst_dpid<>0:
        mytimer2=Timer(2, _timer_func, recurring=True)
     while delay ==0:
        continue
     s1s3_delay=delay
     print "s1s3 CALCULATED DELAY: ", delay
     delay=0
     mytimer2.cancel()
  ### measure s1s4
     src_dpid=s1s4_src
     dst_dpid=s1s4_dst
     if src_dpid<>0 and dst_dpid<>0:
        mytimer3=Timer(2, _timer_func, recurring=True)
     while delay ==0:
        continue
     s1s4_delay=delay
     print "s1s4 CALCULATED DELAY: ", delay
     mytimer3.cancel()
     delay=0
   ### get intent
     h1_ip=event.intent.h1
     h2_ip=event.intent.h2
     demand=event.intent.demand
  ### check if it is possible
     if demand >= min(s1s2_delay,s1s3_delay,s1s4_delay):
        possible_flows=[]
        no_flows=[]
        ## possible paths for given intent
        if s1s2_delay <= demand:
                possible_flows.append('s1s2')
                no_flows.append(len(s1s2_flows))
        else:
                no_flows.append(sys.maxint)
        if s1s3_delay <=demand:
                possible_flows.append('s1s3')
                no_flows.append(len(s1s3_flows))
        else:
                no_flows.append(sys.maxint)
        if s1s4_delay <=demand:
                no_flows.append(len(s1s4_flows))
                possible_flows.append(['s1s4',len(s1s4_flows)])
        else:
                no_flows.append(sys.maxint)
        flow=handle_intent(event.intent,possible_flows,no_flows) ## wyslij info o tym flow do s1
        if flow is not None:
                msg = of.ofp_flow_mod()
                msg.command=of.OFPFC_MODIFY_STRICT
                msg.priority =100
                msg.idle_timeout = flow.timeout
                msg.hard_timeout = 0
                msg.match.dl_type = 0x0800
                msg.match.nw_dst = event.intent.h2
                print "Chosen flow: ", flow.pair_switch
                if flow.pair_switch=='s1s2':
                        msg.actions.append(of.ofp_action_output(port = 4))
                elif flow.pair_switch=='s1s3':
                        msg.actions.append(of.ofp_action_output(port = 5))
                else:
                        msg.actions.append(of.ofp_action_output(port = 6))
                core.openflow.getConnection(s1_dpid).send(msg)

event_handler=EventHandler()
def get_current_array_flows():
	global active_intent_flows
	result=""
	for flow in active_intent_flows:
		result+=flow.pair_switch+" "
	return result
#######Funkcja do okresowego badania QoS, nie wiem czy dziala ale jest prototyp
##[MK]
def _check_conditions():
     global intents,active_intent_flows,delay,s1_dpid,s1s2_src,s1s2_dst,s1s3_src,s1s3_dst,s1s4_src,s1s4_dst,src_dpid,dst_dpid
     print "Checking conditions... "
     ### check lifetime
     while True:
	### check if there are old flows
	for flow in active_intent_flows:
                        diff=time.time()-flow.start_time
                        if diff >= flow.timeout:
                                print 'Refresh of flow: ', flow.pair_switch
                                flow.start_time=time.time()
				intent1=flow.intent
                               # active_intent_flows.remove(flow)
                                #remove_from_lists(flow)
                                #event_handler.raiseEvent(GetIntent,intent1)
				#delete_flow_from_switch(intent1)
				send_info_to_switch(flow,intent1)
     ## measure s1s2
	if len(active_intent_flows)>0:
		print "CURRENT STATE OF FLOWS: ",get_current_array_flows()
     	for flow in active_intent_flows:
		print "Next flow... pair switch currently: ", flow.pair_switch
		delay=0
        	if flow.pair_switch == "s1s2":
                	src_dpid=s1s2_src
                	dst_dpid=s1s2_dst
                	if src_dpid<>0 and dst_dpid<>0:
                        	mytimer4=Timer(2, _timer_func, recurring=True)
			while delay ==0:
                        	continue
               		mytimer4.cancel()
			print "Check conditions: link s1s2 delay=", delay, " and required delay=", flow.intent.demand
                	if flow.intent.demand < delay:
                        #Jesli QoS nie jest juz spelniony to trzeba wywalic flow i znowu zestawic
                        	print 'Zmieniamy QoS s1s2'
				intent1=flow.intent
                        	active_intent_flows.remove(flow)
                        	remove_from_lists(flow)
				delete_flow_from_switch(intent1)
                        	event_handler.raiseEvent(GetIntent,intent1)
        	elif flow.pair_switch == "s1s3":
                	src_dpid=s1s3_src
                	dst_dpid=s1s3_dst
                	if src_dpid<>0 and dst_dpid<>0:
                        	mytimer5=Timer(2, _timer_func, recurring=True)
                	while delay ==0:
                        	continue
                	mytimer5.cancel()
			print "Check conditions: link s1s3 delay=", delay, " and required delay=", flow.intent.demand
                	if flow.intent.demand < delay:
                        #Jesli QoS nie jest juz spelniony to trzeba wywalic flow i znowu zestawic
                        	print 'Zmienianmy QoS s1s3'
				intent1=flow.intent
                        	active_intent_flows.remove(flow)
                        	remove_from_lists(flow)
				delete_flow_from_switch(intent1)
                        	event_handler.raiseEvent(GetIntent,intent1)
        	else:
                	src_dpid=s1s4_src
                	dst_dpid=s1s4_dst
                	if src_dpid<>0 and dst_dpid<>0:
                        	mytimer6=Timer(2, _timer_func, recurring=True)
                	while delay ==0:
                        	continue
                	mytimer6.cancel()
			print "Check conditions: link s1s4 delay: ", delay, " and required delay=", flow.intent.demand
                	if flow.intent.demand < delay:
                        #Jesli QoS nie jest juz spelniony to trzeba wywalic flow i znowu zestawic
                        	print 'Zmieniony QoS s1s4'
				intent1=flow.intent
                       		active_intent_flows.remove(flow)
                        	remove_from_lists(flow)
				delete_flow_from_switch(intent1)
                       		event_handler.raiseEvent(GetIntent,intent1)
        	delay=0
		time.sleep(1)





#### KONIEC NAPISANEJ CZESCI

class myproto(packet_base):
   #My Protocol packet struct
   """
   myproto class defines our special type of packet to be sent all way along including the link between the switches to measure link delays;
   it adds member attribute named timestamp to carry packet creation/sending time by the controller, and defines the
   function hdr() to return the header of measurement packet (header will contain timestamp)
   """
   #For more info on packet_base class refer to file pox/lib/packet/packet_base.py

   def __init__(self):
                packet_base.__init__(self)
                self.timestamp=0
   def hdr(self, payload):
                return struct.pack('!I', self.timestamp) # code as unsigned int (I), network byte order (!, big-endian - the most significant byte of a word at the smallest memory address
###

log = core.getLogger()

s1_dpid=0
s2_dpid=0
s3_dpid=0
s4_dpid=0
s5_dpid=0

s1_p1=0
s1_p4=0
s1_p5=0
s1_p6=0
s2_p1=0
s3_p1=0
s4_p1=0

pre_s1_p1=0
pre_s1_p4=0
pre_s1_p5=0
pre_s1_p6=0
pre_s2_p1=0
pre_s3_p1=0
pre_s4_p1=0

turn=0

def getTheTime():  #function to create a timestamp
  flock = time.localtime()
  then = "[%s-%s-%s" %(str(flock.tm_year),str(flock.tm_mon),str(flock.tm_mday))

  if int(flock.tm_hour)<10:
    hrs = "0%s" % (str(flock.tm_hour))
  else:
    hrs = str(flock.tm_hour)
  if int(flock.tm_min)<10:
    mins = "0%s" % (str(flock.tm_min))
  else:
    mins = str(flock.tm_min)

  if int(flock.tm_sec)<10:
    secs = "0%s" % (str(flock.tm_sec))
  else:
    secs = str(flock.tm_sec)

  then +="]%s.%s.%s" % (hrs,mins,secs)
  return then


def _timer_func ():

  #### DELAY PART
  global start_time, sent_time1, sent_time2, src_dpid, dst_dpid
  #the following executes only when a connection to 'switch0' exists (otherwise AttributeError can be raised)
  if src_dpid <>0 and not core.openflow.getConnection(src_dpid) is None:
    #send out port_stats_request packet through switch0 connection src_dpid (to measure T1)
    core.openflow.getConnection(src_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    sent_time1=time.time() * 1000*10 - start_time #sending time of stats_req: ctrl => switch0
    #print "sent_time1:", sent_time1

    #sequence of packet formating operations optimised to reduce the delay variation of e-2-e measurements (to measure T3)
    f = myproto() #create a probe packet object
    e = pkt.ethernet() #create L2 type packet (frame) object
    e.src = EthAddr("0:0:0:0:0:2")
    e.dst = EthAddr("0:1:0:0:0:1")
    e.type=0x5577 #set unregistered EtherType in L2 header type field, here assigned to the probe packet type
    msg = of.ofp_packet_out() #create PACKET_OUT message object
    msg.actions.append(of.ofp_action_output(port=dst_dpid+2)) #set the output port for the packet in switch0
    f.timestamp = int(time.time()*1000*10 - start_time) #set the timestamp in the probe packet
    #print f.timestamp
    e.payload = f
    msg.data = e.pack()
    core.openflow.getConnection(src_dpid).send(msg)
    #print "=====> probe sent: f=", f.timestamp, " after=", int(time.time()*1000*10 - start_time), " [10*ms]"

  #the following executes only when a connection to 'switch1' exists (otherwise AttributeError can be raised)
  if dst_dpid <>0 and not core.openflow.getConnection(dst_dpid) is None:
    #send out port_stats_request packet through switch1 connection dst_dpid (to measure T2)
    core.openflow.getConnection(dst_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    sent_time2=time.time() * 1000*10 - start_time #sending time of stats_req: ctrl => switch1
    #print "sent_time2:", sent_time2



  #### DELAY
  #global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid,turn
  #core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
  #core.openflow.getConnection(s2_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
  #core.openflow.getConnection(s3_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
  #core.openflow.getConnection(s4_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
  #print getTheTime(), "sent the port stats request to s1_dpid"

  # below, routing in s1 towards h4 (IP=10.0.0.4) is set according to the value of the variable turn
  # turn controls the round robin operation
  # turn=0/1/2 => route through s2/s3/s4, respectively

  #if turn==0:
   #   msg = of.ofp_flow_mod()
    #  msg.command=of.OFPFC_MODIFY_STRICT
     # msg.priority =100
      #msg.idle_timeout = 0
      #msg.hard_timeout = 0
      #msg.match.dl_type = 0x0800
      #msg.match.nw_dst = "10.0.0.4"
      #msg.actions.append(of.ofp_action_output(port = 5))
      #core.openflow.getConnection(s1_dpid).send(msg)
      #turn=1
      #return

  #if turn==1:
   #   msg = of.ofp_flow_mod()
    #  msg.command=of.OFPFC_MODIFY_STRICT
     # msg.priority =100
   #   msg.idle_timeout = 0
  #    msg.hard_timeout = 0
    #  msg.match.dl_type = 0x0800
     # msg.match.nw_dst = "10.0.0.4"
      #msg.actions.append(of.ofp_action_output(port = 6))
      #core.openflow.getConnection(s1_dpid).send(msg)
      #turn=2
      #return

  #if turn==2:
   #   msg = of.ofp_flow_mod()
    #  msg.command=of.OFPFC_MODIFY_STRICT
    #  msg.priority =100
     # msg.idle_timeout = 0
     # msg.hard_timeout = 0
      #msg.match.dl_type = 0x0800
      #msg.match.nw_dst = "10.0.0.4"
      #msg.actions.append(of.ofp_action_output(port = 4))
      #core.openflow.getConnection(s1_dpid).send(msg)
      #turn=0
      #return

def _handle_portstats_received (event):
  #### DELAY
  global start_time, sent_time1, sent_time2, received_time1, received_time2, src_dpid, dst_dpid, OWD1, OWD2

  received_time = time.time() * 1000*10 - start_time
  #measure T1 as of lab guide
  if event.connection.dpid == src_dpid:
     OWD1=0.5*(received_time - sent_time1)
     #print "OWD1: ", OWD1, "ms"

   #measure T2 as of lab guide
  elif event.connection.dpid == dst_dpid:
     OWD2=0.5*(received_time - sent_time2) #originally sent_time1 was here
     #print "OWD2: ", OWD2, "ms"
  #Observe the handling of port statistics provided by this function.
  global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
  global s1_p1,s1_p4, s1_p5, s1_p6, s2_p1, s3_p1, s4_p1
  global pre_s1_p1,pre_s1_p4, pre_s1_p5, pre_s1_p6, pre_s2_p1, pre_s3_p1, pre_s4_p1

  if event.connection.dpid==s1_dpid: # The DPID of one of the switches involved in the link
    for f in event.stats:
      if int(f.port_no)<65534:
        if f.port_no==1:
          pre_s1_p1=s1_p1
          s1_p1=f.rx_packets
          #print "s1_p1->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
        if f.port_no==4:
          pre_s1_p4=s1_p4
          s1_p4=f.tx_packets
          #s1_p4=f.tx_bytes
          #print "s1_p4->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
        if f.port_no==5:
          pre_s1_p5=s1_p5
          s1_p5=f.tx_packets
        if f.port_no==6:
          pre_s1_p6=s1_p6
          s1_p6=f.tx_packets

  if event.connection.dpid==s2_dpid:
     for f in event.stats:
       if int(f.port_no)<65534:
         if f.port_no==1:
           pre_s2_p1=s2_p1
           s2_p1=f.rx_packets
           #s2_p1=f.rx_bytes
     #print getTheTime(), "s1_p4(Sent):", (s1_p4-pre_s1_p4), "s2_p1(Received):", (s2_p1-pre_s2_p1)

  if event.connection.dpid==s3_dpid:
     for f in event.stats:
       if int(f.port_no)<65534:
         if f.port_no==1:
           pre_s3_p1=s3_p1
           s3_p1=f.rx_packets
     #print getTheTime(), "s1_p5(Sent):", (s1_p5-pre_s1_p5), "s3_p1(Received):", (s3_p1-pre_s3_p1)

  if event.connection.dpid==s4_dpid:
     for f in event.stats:
       if int(f.port_no)<65534:
         if f.port_no==1:
           pre_s4_p1=s4_p1
           s4_p1=f.rx_packets
     #print getTheTime(), "s1_p6(Sent):", (s1_p6-pre_s1_p6), "s4_p1(Received):", (s4_p1-pre_s4_p1)

def _handle_ConnectionUp (event):
  #### DELAY
  global src_dpid, readiness, dst_dpid, mytimer, s1s2_src,s1s2_dst,s1s3_src,s1s3_dst,s1s4_src,s1s4_dst

  # waits for connections from all switches, after connecting to all of them it starts a round robin timer for triggering h1-h4 routing changes
  global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
  print "ConnectionUp: ",dpidToStr(event.connection.dpid)

  #remember the connection dpid for the switch
  for m in event.connection.features.ports:
    if m.name == "s1-eth1":
      # s1_dpid: the DPID (datapath ID) of switch s1;
      s1_dpid = event.connection.dpid
      s1s2_src=event.connection.dpid
      s1s3_src=event.connection.dpid
      s1s4_src=event.connection.dpid
    elif m.name == "s2-eth1":
      s2_dpid = event.connection.dpid
      s1s2_dst=event.connection.dpid
    elif m.name == "s3-eth1":
      s3_dpid = event.connection.dpid
      s1s3_dst=event.connection.dpid
    elif m.name == "s4-eth1":
      s4_dpid = event.connection.dpid
      s1s4_dst=event.connection.dpid
    elif m.name == "s5-eth1":
      s5_dpid = event.connection.dpid

  # start 1-second recurring loop timer for round-robin routing changes; _timer_func is to be called on timer expiration to change the flow entry in s1
  #if s1_dpid<>0 and s2_dpid<>0 and s3_dpid<>0 and s4_dpid<>0 and s5_dpid<>0:
   # Timer(1, _timer_func, recurring=True)
def _handle_ConnectionDown (event):
  #Handle connection down - stop the timer for sending the probes
  global mytimer
  print "ConnectionDown: ", dpidToStr(event.connection.dpid)
  mytimer.cancel()

def fill_flows():
  for k in ['10.0.0.4','10.0.0.5','10.0.0.6']:
    checker = False
    for m in intents:
      if k == m.h2:
        checker=True
    if checker==False:
      print "Technical intent for: ", k
      int1=Intent('10.0.0.1',k,9999)
      event_handler.raiseEvent(GetIntent,int1)


def _handle_PacketIn(event):
  ### DELAY
  global start_time, OWD1, OWD2,delay

  received_time = time.time() * 1000*10 - start_time #amount of time elapsed from start_time

  packet = event.parsed
  #print packet

  if packet.type==0x5577 and event.connection.dpid==dst_dpid: #0x5577 is unregistered EtherType, here assigned to probe packets
    #Process a probe packet received in PACKET_IN message from 'switch1' (dst_dpid), previously sent to 'switch0' (src_dpid) in PACKET_OUT.
    #print "Received unknown packet..."
    c=packet.find('ethernet').payload
    d,=struct.unpack('!I', c)  # note that d,=... is a struct.unpack and always returns a tuple
    #print "[ms*10]: received_time=", int(received_time), ", d=", d, ", OWD1=", int(OWD1), ", OWD2=", int(OWD2)
    #print "delay:", int(received_time - d - OWD1 - OWD2)/10, "[ms] <=====" # divide by 10 to normalise to milliseconds
    delay=int(received_time-d-OWD1-OWD2)/10


  global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid

  packet=event.parsed
  #print "_handle_PacketIn is called, packet.type:", packet.type, " event.connection.dpid:", event.connection.dpid

  # Below, set the default/initial routing rules for all switches and ports.
  # All rules are set up in a given switch on packet_in event received from the switch which means no flow entry has been found in the flow table.
  # This setting up may happen either at the very first pactet being sent or after flow entry expirationn inn the switch
  print "PACKET IN"
  if event.connection.dpid==s1_dpid:
     a=packet.find('arp')                                       # If packet object does not encapsulate a packet of the type indicated, find() returns None
     if a and a.protodst=="10.0.0.4":
       msg = of.ofp_packet_out(data=event.ofp)                  # Create packet_out message; use the incoming packet as the data for the packet out
       msg.actions.append(of.ofp_action_output(port=4))         # Add an action to send to the specified port
       event.connection.send(msg)                               # Send message to switch

     if a and a.protodst=="10.0.0.5":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=5))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.6":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=6))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.1":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=1))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.2":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=2))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.3":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=3))
       event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800         # rule for IP packets (x0800)
     msg.match.nw_dst = "10.0.0.1"
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.2"
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.3"
     msg.actions.append(of.ofp_action_output(port = 3))
     event.connection.send(msg)

     thread.start_new_thread(fill_flows,())
 ### zakomentowane bo to ma routing robic
     #msg = of.ofp_flow_mod()
     #msg.priority =100
     #msg.idle_timeout = 0
     #msg.hard_timeout = 1
     #msg.match.dl_type = 0x0800
     #msg.match.nw_dst = "10.0.0.4"
     #msg.actions.append(of.ofp_action_output(port = 4))
     #event.connection.send(msg)

     #msg = of.ofp_flow_mod()
     #msg.priority =100
     #msg.idle_timeout = 0
     #msg.hard_timeout = 0
     #msg.match.dl_type = 0x0800
     #msg.match.nw_dst = "10.0.0.5"
     #msg.actions.append(of.ofp_action_output(port = 5))
     #event.connection.send(msg)

     #msg = of.ofp_flow_mod()
     #msg.priority =100
     #msg.idle_timeout = 0
     #msg.hard_timeout = 0
     #msg.match.dl_type = 0x0800
     #msg.match.nw_dst = "10.0.0.6"
     #msg.actions.append(of.ofp_action_output(port = 6))
     #event.connection.send(msg)

  elif event.connection.dpid==s2_dpid:
     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0806           # rule for ARP packets (x0806)
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0806
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

  elif event.connection.dpid==s3_dpid:
     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0806
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0806
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

  elif event.connection.dpid==s4_dpid:
     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0806
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 1
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0806
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 2
     msg.match.dl_type=0x0800
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

  elif event.connection.dpid==s5_dpid:
     a=packet.find('arp')
     if a and a.protodst=="10.0.0.4":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=4))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.5":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=5))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.6":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=6))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.1":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=1))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.2":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=2))
       event.connection.send(msg)

     if a and a.protodst=="10.0.0.3":
       msg = of.ofp_packet_out(data=event.ofp)
       msg.actions.append(of.ofp_action_output(port=3))
       event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.1"
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =10
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.in_port = 6
     msg.actions.append(of.ofp_action_output(port = 3))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.1"
     msg.actions.append(of.ofp_action_output(port = 1))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.2"
     msg.actions.append(of.ofp_action_output(port = 2))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.3"
     msg.actions.append(of.ofp_action_output(port = 3))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.4"
     msg.actions.append(of.ofp_action_output(port = 4))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.5"
     msg.actions.append(of.ofp_action_output(port = 5))
     event.connection.send(msg)

     msg = of.ofp_flow_mod()
     msg.priority =100
     msg.idle_timeout = 0
     msg.hard_timeout = 0
     msg.match.dl_type = 0x0800
     msg.match.nw_dst = "10.0.0.6"
     msg.actions.append(of.ofp_action_output(port = 6))
     event.connection.send(msg)

#As usually, launch() is the function called by POX to initialize the component (routing_controller.py in our case)
#indicated by a parameter provi
def test():
  time.sleep(5) ### czeka az wszystkie wezly wstana
  global intents,delay,src_dpid, dst_dpid
  ### tutaj tworzenie intentow
  for intent in intents:
  	event_handler.raiseEvent(GetIntent,intent)
##[MK]
  thread.start_new_thread(_check_conditions,())
def launch ():
  global start_time
  start_time = time.time() * 1000*10 # factor *10 applied to increase the accuracy for short delays (capture tenths of ms)
  print "start_time:", start_time/10
  # core is an instance of class POXCore (EventMixin) and it can register objects.
  # An object with name xxx can be registered to core instance which makes this object become a "component" available as pox.core.core.xxx.
  # for examples see e.g. https://noxrepo.github.io/pox-doc/html/#the-openflow-nexus-core-openflow
  core.openflow.addListenerByName("PortStatsReceived",_handle_portstats_received) # listen for port stats , https://noxrepo.github.io/pox-doc/html/#statistics-events
  core.openflow.addListenerByName("ConnectionUp", _handle_ConnectionUp) # listen for the establishment of a new control channel with a switch, https://noxrepo.github.io/pox-doc/html/#connectionup
  core.openflow.addListenerByName("PacketIn",_handle_PacketIn) # listen for the reception of packet_in message from switch, https://noxrepo.github.io/pox-doc/html/#packetin
  core.openflow.addListenerByName("ConnectionDown", _handle_ConnectionDown)
  event_handler.addListener(GetIntent,_handler_GetIntent)
  thread.start_new_thread(test,())
