import grpc
import time
import threading as trd
import grpc_pb2
import grpc_pb2_grpc

clientId = input("Id: ")
channel = grpc.insecure_channel('localhost:50051')
stub = grpc_pb2_grpc.PubsubStub(channel)
def publish(topic, context):
    print("Publish message in {}:{}".format(topic, context))
    response = stub.publish(grpc_pb2.publishRequest(topic=topic, context=context))
    print(response.message)
def browse(topic):
    print("Browse topic {}".format(topic))
    response = stub.browse(grpc_pb2.browseRequest(topic=topic))
    for msg in response:
        print(msg.message)
def _subcribe(topic, TTL):
    for msg in stub.subcribe(grpc_pb2.subRequest(topic=topic, clientId=clientId, TTL=TTL)):
        print("Receive message from {}:{}".format(topic, msg.message))

def subcribe(topic, TTL=20):
    print("Subscribed {} successfully.".format(topic))
    thrd = trd.Thread(target=_subcribe, args=(topic,TTL))
    thrd.start()
        
publish('test_topic', 'message1')  
browse('test_topic')
time.sleep(5)
publish('test_topic', 'message2')
subcribe('test_topic', 20)
publish('test_topic', 'message3')
time.sleep(6)
browse('test_topic')