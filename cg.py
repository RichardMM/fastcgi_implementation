import logging
from logging import FileHandler, Formatter
from socket import socket, AF_INET, SOCK_STREAM
import sys
import os
import struct
from typing import Dict

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

f_handler = FileHandler('C:\\Users\\rmacharia\\Documents\\engagements\\programming\\fastcgi_tests\\logs.log')
f_format = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_handler.setFormatter(f_format)
f_handler.setLevel(logging.DEBUG)
logger.addHandler(f_handler)

#Constants
ROLES = {1:"FCGI_RESPONDER", 2:"FCGI_AUTHORIZER", 3:"FCGI_FILTER"}
RECORD_TYPES = {1: "FCGI_BEGIN_REQUEST",2:"FCGI_ABORT_REQUEST",3:"FCGI_END_REQUEST",
                4: "FCGI_PARAMS",              
                5:"FCGI_STDIN" ,             
                6:"FCGI_STDOUT" ,             
                7:"FCGI_STDERR",
                8:"FCGI_DATA",          
                9:"FCGI_GET_VALUES",          
                10:"FCGI_GET_VALUES_RESULT",
                11: "FCGI_UNKNOWN_TYPE"}
class FcgiRecord:
    def __init__(self, args):
        self.version = args[0]
        self.rec_type= args[1]
        self.request_id= (args[2] << 8) + args[3]
        self.content_length = (args[4] << 8) + args[5]
        self.padding_length = args[6]
        self.reserved = args[7]
        self.content_data =None
        self.padding_data = None
      

    def __repr__(self):
        return f'''{self.version=}, self.rec_type={RECORD_TYPES[self.rec_type]},
                 {self.request_id=}, {self.content_length=},
                 {self.padding_length=},{self.content_data=}'''
    def pack_struct(self):
        
        if self.padding_data is None:
            self.padding_length = 0

        if self.content_length!=0:
            
            return struct.pack(f'>BBHHBB',
                    self.version, self.rec_type,
                    self.request_id,self.content_length,
                    0,0) + self.content_data
        else:
            return struct.pack(f'>BBHHBB',
                    self.version, self.rec_type,
                    self.request_id,0,
                    0,0)

class FcgiApplicationRequest:
    def __init__(self, request_id, stream):
        self.request_id = request_id

        self.param_records:list = []

        self.stdin_records:list = []
        self.params:dict= {}
        self.content = None
        self.stream = stream
        self.params_complete = False
        self.stdin_complete = False



    def generate_reponse(self):

        res_body = '''Hello World''' 
        resp_header = f'''Status: 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: 11\r\n\r\n'''
        

        return resp_header .encode('iso-8859-1'),res_body.encode('iso-8859-1')

    def generate_fcgi_stdout(self):
        out_content = self.generate_reponse()
        out_records = []
        max_length = 65535
        for content in out_content: 
            content_length = len(content)
            

           
            multiple = content_length//max_length

            rem = int(content_length%max_length)

            for i in range(0,int(multiple)):
                length = max_length*(i+1)
                data = content[max_length*i:length]
                std_out = FcgiRecord([1,6,0,self.request_id,0,length,None,1])
                std_out.content_data = data
                out_records.append(std_out)

            # append remainder
            rem_record = FcgiRecord([1,6,0,self.request_id,0,rem,None,1])
            rem_record.content_data = content[multiple*max_length:]
            out_records.append(rem_record)


        return out_records

    def end_request(self):
        logger.debug(f'SENDING END_Request {self.request_id}')
        stream_no = self.stream.fileno()
        end_req = FcgiRecord([1,3,0,self.request_id,0,8,8,0])
        end_req.content_data = struct.pack('>5B3B',0,0,0,0,0,0,0,0)
        out_data = self.generate_fcgi_stdout()
        empty_std_out = FcgiRecord([1,6,0,self.request_id,0,0,None,1])
        
        empty_std_out_strct = empty_std_out.pack_struct()
        for item in out_data:
      
            to_send = item.pack_struct()
            logger.debug(f'{to_send = }')
            os.write(stream_no,to_send)
         
        os.write(stream_no,empty_std_out_strct)
        logger.debug(empty_std_out_strct )
           
        end_req_strct = end_req.pack_struct()
        logger.debug(end_req_strct)
        os.write(stream_no,end_req_strct)
        stream.flush()



    def add_record(self, record:FcgiRecord):
        if "PARAM" in RECORD_TYPES[record.rec_type]:
            self.param_records.append(record)
            if record.content_length==0:
                self.params_complete=True
        elif "FCGI_STDIN" in RECORD_TYPES[record.rec_type]:
            self.stdin_records.append(record)
            if record.content_length==0:
                self.stdin_complete=True
        if self.params_complete and self.stdin_complete:
            self.end_request()
      
    

class RequestManager:
    def __init__(self, stream):
        self.req_dict:Dict[int, FcgiApplicationRequest] = {}
        self.stream = stream
    
    def allocate_record(self, record:FcgiRecord):
        req_id = record.request_id
        if RECORD_TYPES[record.rec_type] in ["FCGI_PARAMS", "FCGI_STDIN"]:
            if req_id not in self.req_dict.keys(): 
                req_obj = FcgiApplicationRequest(req_id, self.stream)
                self.req_dict[record.request_id]=req_obj

            self.req_dict[record.request_id].add_record(record)

            #logger.debug(f'Record Allocated: {req_id}')
        else:

            logger.warning(f'Record Was not Allocated: {record}')

def get_args():

    try:
        import msvcrt
        stream = sys.stdin.detach()
        
        
        msvcrt.setmode(stream.fileno(), os.O_BINARY)
        request_manager = RequestManager(stream)

        while True:
            rec_head = stream.read(8)
            unpacked = struct.unpack(">8B",rec_head)
            rec = FcgiRecord(unpacked)
            rec.content_data = stream.read(rec.content_length)
            stream.read(rec.padding_length)
            
            request_manager.allocate_record(rec) 
            
       
    except Exception:
        logger.exception("Error in main Loop")
    

def listen_sock():
    
    logger.debug('function was called')
    from_env = os.environ.get('FCGI_LISTENSOCK_FILENO', None)
    logger.debug(f'Environment socket:{from_env}')
    defult_sock = sys.stdin.fileno() 
    no = defult_sock if from_env is None else defult_sock
    try:
        with socket(AF_INET,SOCK_STREAM,fileno=no) as s:
            s.listen()
            conn, address = s.accept()
            with conn:
                logger.debug(f'Client is in address: {address}')
                while True:
                    data = conn.recv(1024)
                    if data is not None:
                        logger.debug(data)
    except Exception as e:
        logger.exception(e)


if __name__ == "__main__":
    get_args()
