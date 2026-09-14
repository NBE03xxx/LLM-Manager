import json,os,socket
from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/api/version': value={'version':'0.33.2'}
  elif self.path=='/api/tags': value={'models':[]}
  else: self.send_error(404); return
  body=json.dumps(value,separators=(',',':')).encode(); self.send_response(200)
  self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body)))
  self.end_headers(); self.wfile.write(body)
 def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',11434),H)
address=os.environ['NOTIFY_SOCKET']; address=('\0'+address[1:]) if address.startswith('@') else address
notice=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); notice.connect(address); notice.sendall(b'READY=1'); notice.close()
server.serve_forever()
