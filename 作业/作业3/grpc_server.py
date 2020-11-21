from threading import Event
from concurrent import futures
import time
import grpc


import grpc_pb2
import grpc_pb2_grpc

class Pubsub(object):
    """一个本地的Pubsub模型"""
    def __init__(self):
        self.storage = {}
        self.event = {}
        
    def publish(self, topic, message):
        """发布主题消息 返回发布是否成功"""
        msg = ""
        if topic not in self.storage:
            self.storage[topic] = [{'createTime': time.time(), 'message': message}]
            msg += "create topic: {}\n".format(topic)
        else:
            self.storage[topic].append({'createTime': time.time(), 'message': message})
        if topic in self.event:
            for client in self.event[topic]:
                self.event[topic][client].set()
        msg += "publish successful"
        return msg
    
    def gen_msg(self, msg):
        """将存储的消息转化为可读消息"""
        return str(msg['createTime']) + ": " + msg['message']
    
    def refresh(self, TTL=10):
        """每个一段时间刷新存储的消息 可以控制消息在服务器存储的时间"""
        ddl = time.time() - 10
        for topic in self.storage:
            while len(self.storage[topic]) and self.storage[topic][0]['createTime'] <= ddl:
                del self.storage[topic][0]
                
    def browse(self, topic):
        """浏览主题 返回主题所有消息的generator"""
        if topic not in self.storage:
            return ["topic not created"]
        for msg in self.storage[topic]:
            yield self.gen_msg(msg)
    
    def subcribe(self, topic, clientId, TTL=20):
        """订阅主题 返回主题新消息的generator"""
        if topic not in self.event:
            self.event[topic] = {}
        self.event[topic][clientId] = Event()
        createTime = time.time()
        remainTime = TTL
        while True:
            self.event[topic][clientId].wait(remainTime)
            remainTime = TTL - (time.time() - createTime)
            if remainTime <= 0:
                break
            yield self.gen_msg(self.storage[topic][-1])
            self.event[topic][clientId].clear()

class PubsubService(grpc_pb2_grpc.Pubsub):
    """实现grpc的相关过程"""
    def __init__(self):
        self.pubsub = Pubsub() 
        
    def publish(self, request, context): 
        msg = self.pubsub.publish(request.topic, request.context)
        return grpc_pb2.reply(message = msg)
    
    def browse(self, request, context):
        for msg in self.pubsub.browse(request.topic):
            yield grpc_pb2.reply(message=msg)  # 
    
    def subcribe(self, request, context):  
        for msg in self.pubsub.subcribe(request.topic, request.clientId, request.TTL):   
            yield grpc_pb2.reply(message=msg)

if __name__ == '__main__':
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10)) 
    pubsubServe = PubsubService() 
    grpc_pb2_grpc.add_PubsubServicer_to_server(pubsubServe, server) 
    server.add_insecure_port('[::]:50051')
    server.start()
    try:
        while True:
            time.sleep(1)
            pubsubServe.pubsub.refresh() 
    except KeyboardInterrupt:
        server.stop(0)