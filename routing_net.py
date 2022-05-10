#!/usr/bin/python
 
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.node import Controller 
from mininet.cli import CLI
from threading import Timer
from functools import partial
from mininet.node import RemoteController
import os
import thread
import time
# Topology: switches interconnected in diamond topology (3 parallel paths, no cross-links); 3 hosts on each side of the diamond
s1=s2=s3=s4=None

class MyTopo(Topo):
    "Single switch connected to n hosts."
    def __init__(self):
        Topo.__init__(self)
        ### const part
	s1=self.addSwitch('s1')
        s2=self.addSwitch('s2')
        s3=self.addSwitch('s3')
        s4=self.addSwitch('s4')
        s5=self.addSwitch('s5')
        h1=self.addHost('h1')
        h2=self.addHost('h2')
        h3=self.addHost('h3')
        h4=self.addHost('h4')
        h5=self.addHost('h5')
        h6=self.addHost('h6')
	
        self.addLink(h1, s1, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(h2, s1, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(h3, s1, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s1, s2, bw=1, delay='200ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s1, s3, bw=1, delay='50ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s1, s4, bw=1, delay='10ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s2, s5, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s3, s5, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s4, s5, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s5, h4, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s5, h5, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
        self.addLink(s5, h6, bw=1, delay='0ms', loss=0, max_queue_size=1000, use_htb=True)
		
def cDelay1(delays): #function called back to set the link delay to 50 ms; both d$
       global s1,s2,s3,s4
       #switch.cmdPrint('ethtool -K s0-eth1 gro off') #not supported by VBox, u$
       s1.cmdPrint('tc qdisc del dev s1-eth4 root')
       s1.cmdPrint('tc qdisc add dev s1-eth4 root handle 10: netem delay {}'.format(delays[0]))
       s2.cmdPrint('tc qdisc del dev s2-eth1 root')
       s2.cmdPrint('tc qdisc add dev s2-eth1 root handle 10: netem delay {}'.format(delays[0]))
       #switch1.cmdPrint('ethtool -K s1-eth0 gro off') #not supported by VBox, $
       s1.cmdPrint('tc qdisc del dev s1-eth5 root')
       s1.cmdPrint('tc qdisc add dev s1-eth5 root handle 10: netem delay {}'.format(delays[1]))
       s3.cmdPrint('tc qdisc del dev s3-eth1 root')
       s3.cmdPrint('tc qdisc add dev s3-eth1 root handle 10: netem delay {}'.format(delays[1]))
       ### 
       s1.cmdPrint('tc qdisc del dev s1-eth6 root')
       s1.cmdPrint('tc qdisc add dev s1-eth6 root handle 10: netem delay {}'.format(delays[2]))
       s4.cmdPrint('tc qdisc del dev s4-eth1 root')
       s4.cmdPrint('tc qdisc add dev s4-eth1 root handle 10: netem delay {}'.format(delays[2]))
def change_delay(*test_cases):
	time.sleep(30)
        for test in test_cases:
		time.sleep(10)
		cDelay1(test)
def perfTest():
    "Create network and run simple performance test"
    global s1,s2,s3,s4
    test_cases=(['200ms','50ms','10ms'],['15ms','44ms','123ms'],['100ms','10ms','23ms']) ### to add test cases
    thread.start_new_thread(change_delay,(test_cases))
    topo = MyTopo()
    #net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink, controller=POXcontroller1)
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink, controller=partial(RemoteController, ip='127.0.0.1', port=6633))
    net.start()
    print "Dumping host connections"
    dumpNodeConnections(net.hosts)
    h1,h2,h3=net.get('h1','h2','h3')
    h4,h5,h6=net.get('h4','h5','h6')
    s1,s2,s3,s4=net.get('s1','s2','s3','s4')
    h1.setMAC("0:0:0:0:0:1")
    h2.setMAC("0:0:0:0:0:2")
    h3.setMAC("0:0:0:0:0:3")
    h4.setMAC("0:0:0:0:0:4")
    h5.setMAC("0:0:0:0:0:5")
    h6.setMAC("0:0:0:0:0:6")
    thread.start_new_thread(change_delay,(test_cases))

    CLI(net) # launch simple Mininet CLI terminal window
    
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    perfTest()