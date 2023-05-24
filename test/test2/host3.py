#GBN协议实现
import socket
import threading
import queue
import os
from enum import Enum
import time
import pickle
import json
import random

# 设置配置文件路径
config_file_path="config3.json"

# ---------------------------------------------------------------------------- #
# 载入配置文件,全局变量定义
# ---------------------------------------------------------------------------- #
with open(config_file_path,"r") as f:
    config=json.load(f)

DATA_SIZE = config["DataSize"]      #每次读文件数据块的大小
RECEIVE_BUFFER_SIZE= config["ReceiveBufferSize"]    #udp socket接收数据块的缓冲区大小
TIMEOUT=config["Timeout"]   #GBN超时上限
LISTEN_TIMEOUT=config["listenTimeOut"]  #udp socket监听超时上限
EMPTY_TIMEOUT=config["QueueEmptyTime"]
ERROR_RATE=config["ErrorRate"]  #错误率
LOST_RATE=config["LostRate"]    #丢失率
SWSize = config["SWSize"]   #GBN窗口大小
InitSeqNo=config["InitSeqNo"]   #GBN开始窗口序号
local_port=config["UPDPort"]    #本地udp socket监听端口
target_port=config["TargetPort"]    #发送文件的目的端口
input_file_name=config["InputFileName"] #发送文件名（需要在当前目录下）
host_file_tiltle=config["HostName"] #当前端口名标识

# 线程管理相关
connection_pool={} #建立socket address与gbn_connection对象的映射
# ---------------------------------------------------------------------------- #
# 类定义
# ---------------------------------------------------------------------------- #

# 事件类型：发送事件和接收事件
class MSG_STATE(Enum):
    SEND=0
    RECEIVE=1

# frame
class frame:
    def __init__(self, kind,next_frame_to_send, frame_expected) :
        self.kind = kind   #标记帧类型，0是数据，1是纯ack；
        self.seq = next_frame_to_send   #发送帧的序号
        self.ack = (frame_expected+ SWSize)%(SWSize+1)    #ack要“后退”一位，从首位开始错开; 
        self.info = b'' #字节流类型
        self.checksum = 0   # 只对info进行checksum

# 线程类，处理核心发送和接收事件，每和一个socket开始通信就创建一个
class gbn_connection(threading.Thread):
    def __init__(self,local_socket,client_address):
        threading.Thread.__init__(self)
        #socket连接信息
        self.local_socket=local_socket
        self.client_address=client_address
        #消息队列
        self.host_msg=queue.Queue()
        # 发送文件数据缓冲区
        self.buffer=[]   
        self.buffer_size=0   #buffer大小
        self.buffer_point=0  #指向发送包的指针
        #GBN相关变量初始值
        self.next_frame_to_send = InitSeqNo  #下一发送包序号
        self.ack_expected = InitSeqNo    # 期望接收到的包序号
        self.frame_expected = InitSeqNo  #捎带ack的序号
        self.window_num = 0   #已经使用的window数量.
        #计时相关
        self.is_set_timer=False  #是否已经开启计时器
        self.is_end_timer=False   #是否开始终止计时
        self.start_timer=0      #GBN计时器
        self.end_timer=0      #终止计时的开始
        #文件相关
        self.isdamage=False  #标志包的数据是否损坏
        self.receive_content=b'' #存储收到的文件数据
        self.is_send_end=False     #标识发送是否完成
        #日志相关
        self.log_content=""    #存储日志
        self.send_num=0         #发送次数
        self.receive_num=0      #接收次数
        self.time_start=0       #线程开始运行时的时间戳，用于记录总时间

    # 预装载待发送文件至内存中
    def load_data(self):
        with open(input_file_name+".txt",'rb') as f:
            while True: 
                data_bytes=f.read(DATA_SIZE)
                if not data_bytes:  #读到文件尾，退出
                    break
                self.buffer.append(data_bytes)
                self.buffer_size+=1
    # ---------------------------------------------------------------------------- #
    # 处理消息的核心线程函数
    # ---------------------------------------------------------------------------- #
    def run(self):
        self.time_start=time.time()
        self.load_data()
        while True:
            #一次发送多个帧，直到用完window数阻塞
            while(not self.is_send_end and self.window_num<SWSize):
                data_PDU=self.create_PDU(0,self.next_frame_to_send,self.frame_expected,self.buffer,self.buffer_point)
                self.host_msg.put((MSG_STATE.SEND,data_PDU))  #发送动作存到msg_pool中，排队等待线程处理
                self.buffer_point+=1
                self.window_num+=1
                self.next_frame_to_send=(self.next_frame_to_send+1)%(SWSize+1)
                #记录日志
                self.send_num+=1
                self.log_content+="SEND:{},pdu_to_send={},status=New,ackNo={}\n".format(self.send_num,data_PDU.seq,data_PDU.ack)
                #判断是否发送完毕
                if(self.buffer_point>=self.buffer_size):
                    self.is_send_end=True
                    break   
            #检查是否超时
            if (self.is_set_timer):
                if((time.time()*1000 - self.start_timer)> TIMEOUT):
                    #print("TIMEOUT!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                    #如果超时，重新从ack_expected开始传输
                    self.next_frame_to_send=self.ack_expected
                    self.buffer_point-=self.window_num
                    #关闭timer，下一次开始发送时才开始重置计时
                    self.is_set_timer=False
                    #将重传事件放入消息队列中
                    for _ in range(self.window_num):
                        data_PDU=self.create_PDU(0,self.next_frame_to_send,self.frame_expected,self.buffer,self.buffer_point)
                        self.host_msg.put((MSG_STATE.SEND,data_PDU))  #发送动作存到msg_pool中，排队等待线程处理
                        self.buffer_point+=1
                        self.next_frame_to_send=(self.next_frame_to_send+1)%(SWSize+1)
                        #记录日志
                        self.send_num+=1
                        self.log_content+="SEND:{},pdu_to_send={},status=TO,ackNo={}\n".format(self.send_num,data_PDU.seq,data_PDU.ack)
            #开始处理消息
            # 检查消息队列是否为空
            if (self.host_msg.empty()):
                if(not self.is_end_timer):       
                    self.is_end_timer=True   #消息队列为空，开始终止计时
                    self.end_timer=time.time()   
            else:
                self.is_end_timer=False  #消息队列非空，关闭终止计时
                #获取消息队列中的事件，开始处理
                event,data_frame=self.host_msg.get()
                #发送消息
                if(event==MSG_STATE.SEND):
                    #开始计时, 发送纯ack时不开计时器
                    if(not self.is_set_timer and data_frame.kind == 0 ):  
                        self.start_timer=time.time()*1000
                        self.is_set_timer=True
                        #print("start timer!!!!!!!!!!!!!!!!!!!")
                    # 按照LOST_RATE模拟丢包
                    if(not self.is_lost_frame()):
                        self.local_socket.sendto(to_physical_layer(data_frame),self.client_address)
                    else:
                        pass
                        #print("loss")
                    #print("send a packet: seq={}, kind={}, ack={}".format(data_frame.seq,data_frame.kind,data_frame.ack))
                #接收消息
                elif(event==MSG_STATE.RECEIVE):
                    # 检测包是否损坏
                    checksum=self.calc_frame_checksum(data_frame)
                    if(checksum == data_frame.checksum):
                        if(data_frame.kind==0):
                            #检查是否是期望的包
                            if(data_frame.seq == self.frame_expected):
                                self.receive_num+=1
                                self.log_content+="RECV:{},pdu_exp={},pdu_recv={},status=OK\n".format(self.receive_num,self.frame_expected,data_frame.seq)
                                #更新frame_expected, 添加内容到receive_conten
                                self.frame_expected=(self.frame_expected+1)%(SWSize+1)
                                self.receive_content+=data_frame.info
                                #print("receive a packet: seq={}, kind={}, ack={}".format(data_frame.seq,data_frame.kind,data_frame.ack))
                                #传送ack
                                if(self.is_send_end):
                                    #如果已经主机已经结束传输，那么将纯的ack装入消息队列中
                                    data_PDU=self.create_PDU(1,self.next_frame_to_send,self.frame_expected,self.buffer,self.buffer_point)
                                    self.host_msg.put((MSG_STATE.SEND ,data_PDU))
                                else:
                                    #send没有结束，就等待下次发送数据时捎带即可
                                    pass
                            else:
                                self.receive_num+=1
                                self.log_content+="RECV:{},pdu_exp={},pdu_recv={},status=NoErr\n".format(self.receive_num,self.frame_expected,data_frame.seq)
                                #不是期望的包，丢弃
                                pass
                        else:
                            #纯ack
                            pass
                        #无论是ack or piggy, 都只采用cultimative方式更新本主机的sender window: ack_expected and window_size
                        while(self.between(self.ack_expected,data_frame.ack,self.next_frame_to_send)):
                            self.is_set_timer=False
                            self.window_num-=1
                            self.ack_expected=(self.ack_expected+1)%(SWSize+1)
                    else:
                        self.receive_num+=1
                        self.log_content+="RECV:{},pdu_exp={},pdu_recv={},status=DataErr\n".format(self.receive_num,self.frame_expected,data_frame.seq)
                        #print("error")
            #print(len(self.receive_content))
            # 判断文件是否传输完成，终止进程
            #print("{}".format(window_num))
            #print("{}".format(is_end_timer))
            if(self.is_end_timer):
                #print("{}".format(time.time()-end_timer))
                if ((time.time()-self.end_timer)>EMPTY_TIMEOUT):
                    self.log_content+="total_time:{}s".format(time.time()-self.time_start)
                    print("Thread Terminate!")
                    #输出接收文件
                    output_filepath=host_file_tiltle+"/receive/from_"+str(self.client_address[0])+"_"+str(self.client_address[1])+"_"+input_file_name+".txt"
                    if not os.path.exists(os.path.dirname(output_filepath)):
                        os.makedirs(os.path.dirname(output_filepath))
                    with open(output_filepath,"wb") as f:
                        f.write(self.receive_content)
                    #输出日志文件
                    output_filepath=host_file_tiltle+"/log/from_"+str(self.client_address[0])+"_"+str(self.client_address[1])+"_"+input_file_name+".txt"
                    if not os.path.exists(os.path.dirname(output_filepath)):
                        os.makedirs(os.path.dirname(output_filepath))
                    with open(output_filepath,"w") as f:
                        f.write(self.log_content)
                    print("done!")
                    break
    
    def is_lost_frame(self):
        return LOST_RATE>random.randint(1,100)
    def is_error_frame(self):
        return ERROR_RATE>random.randint(1,100)
    # 计算CRC-CCITT
    # using the standard polynomial x^16 + x^12 + x^5 + 1 .
    def calc_crc_ccitt(self,data):
        poly = 0x1021  
        crc_reg = 0xFFFF
        for byte in data:   #对每个字节进行计算
            crc_reg ^= (byte << 8)
            for _ in range(8):
                if (crc_reg & 0x8000):  #检查最高位是否为1
                    crc_reg = (crc_reg << 1) ^ poly
                else:
                    crc_reg <<= 1
            crc_reg &= 0xFFFF   #保证CRC始终为16位（python整型无限长）
        return crc_reg

    # 计算整个帧的checksum
    def calc_frame_checksum(self,data_frame):
        data_bytes=b''
        data_bytes+=bytes(data_frame.kind)
        data_bytes+=bytes(data_frame.seq)
        data_bytes+=bytes(data_frame.ack)
        data_bytes+=bytes(data_frame.info)
        return self.calc_crc_ccitt(data_bytes)

    # 将本地文件的数据块组装成帧
    def create_PDU(self,kind,next_frame_to_send,ack_expected,buffer,point):
        data_frame=frame(kind,next_frame_to_send,ack_expected)
        if(kind ==0):
            info=buffer[point]
            data_frame.info=info
        #按照EORROR概率产生帧错误
        if(not self.is_error_frame()):
            data_frame.checksum=self.calc_frame_checksum(data_frame) #对整个帧checksum
        return data_frame


    # 判断是否需要累计确认
    def between(self,a,b,c):
        if(((a<=b) and (b<c))or((c<a)and (a<=b)) or ((b<c)and(c<a))):
            return True
        else:
            return False



# ---------------------------------------------------------------------------- #
# 其他函数定义
# ---------------------------------------------------------------------------- #

# 进行udp套接字的创建和配置
def set_udp_socket():
    # 创建UDP套接字,绑定到本地端口
    udp_socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    host=socket.gethostbyname(socket.gethostname())
    local_address=(host,local_port)
    target_address=(host,target_port)
    udp_socket.bind(local_address)
    # 设置socket最长监听时间
    udp_socket.settimeout(LISTEN_TIMEOUT)
    return udp_socket,target_address

#将字节流还原到帧结构中
def from_physical_layer(data_bytes):
    # data_frame=frame(int(data_bytes[0]),int(data_bytes[1]),int(data_bytes[2]))
    # data_frame.info=data_bytes[3,len(data_bytes)-2]
    # data_frame.checksum=data_bytes[-2:]
    return pickle.loads(data_bytes)
    

#帧结构转化为字节流，然后传输
def to_physical_layer(data_frame):
    # data_bytes=b''
    # data_bytes+=bytes(data_frame.kind)
    # data_bytes+=bytes(data_frame.seq)
    # data_bytes+=bytes(data_frame.ack)
    # data_bytes+=bytes(data_frame.info)
    # data_bytes+=struct.pack('H',data_frame.checksum)
    return pickle.dumps(data_frame)

# ---------------------------------------------------------------------------- #
# 主函数
# ---------------------------------------------------------------------------- #
def main():
    #创建并配置好UDP连接
    udp_socket,target_address=set_udp_socket()
    # 创建一个线程类,主动发送文件
    new_connection=gbn_connection(udp_socket,target_address)
    connection_pool[target_address]=new_connection
    new_connection.daemon=True
    new_connection.start()
    #print("start a thread by sending")
    # 主线程，循环接收数据
    while(True):
        try:
            data_bytes,client_address=udp_socket.recvfrom(RECEIVE_BUFFER_SIZE)  #使用UDP接口，接收client传来的数据
            data_frame=from_physical_layer(data_bytes)   #将字节流对象反序列化为frame对象
            #将数据添加到对应线程处理对象的消息队列中
            if (client_address in connection_pool):    
                connection_pool[client_address].host_msg.put((MSG_STATE.RECEIVE,data_frame))    
            else:         #如果对于connection对象没建立，则创建并开启线程对象
                new_connection=gbn_connection(udp_socket,client_address)
                connection_pool[client_address]=new_connection
                new_connection.host_msg.put((MSG_STATE.RECEIVE,data_frame))
                new_connection.daemon=True
                new_connection.start()
                #print("start a thread by receiving")
        except KeyboardInterrupt:
            break
        except socket.timeout:
            print("socket time out")
        except socket.error as e:
                print(e)


if __name__=='__main__':
    main()

