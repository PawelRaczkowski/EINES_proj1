This repo has been designed for project no 1 of EINES on WUT.

This project performs simulation of POX SDN controller by means of two files:
* routing_net.py-> This script creates Mininet infrastructure and periodically change delays on s1-s2, s1-s3, s1-s4 links.
* routing_controller.finished.py -> this script runs POX SDN controller which handles with setting flows on switches especially on the s1 switch according to our assumption about providing QoS in our network (number of flows on s1s2 s1s3 s1s4 links should be as equal as it is possible)



To run this simulation:
1. Run data plane by:
sudo python routing_net.py
2. Within few seconds run control plane by following command:
sudo python pox.py routing_controller_finished

During this simulation on the screen in routing_net.py terminal you should observe text (this is a result of cmdPrint execution)- but it means that thread responsible for changing delays is in working state.
On the routing_controller_finished.py terminal you should see messages about changing flows as a result of rerouting performed by control plane. You should be able to observe some results of delay calculations as intermediate steps in rerouting process.
