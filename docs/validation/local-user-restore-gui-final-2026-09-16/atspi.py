import json,sys,time
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.init()
mode=sys.argv[1]
def safe(call,default=None):
 try:return call()
 except Exception:return default
def walk(node,depth=0):
 yield node
 if depth>=12:return
 for i in range(safe(node.get_child_count,0) or 0):
  child=safe(lambda:node.get_child_at_index(i))
  if child is not None:yield from walk(child,depth+1)
def nodes():
 desktop=Atspi.get_desktop(0); result=[]
 for i in range(desktop.get_child_count()):
  app=desktop.get_child_at_index(i)
  values=list(walk(app))
  if any((safe(x.get_name,'') or '')=='LLM Manager' for x in values):result.extend(values)
 return result
def describe(node):
 box=safe(lambda:node.get_extents(Atspi.CoordType.SCREEN))
 states=safe(node.get_state_set)
 return {'name':safe(node.get_name,'') or '','role':safe(node.get_role_name,'unknown') or 'unknown',
  'actions':[safe(lambda i=i:node.get_action_name(i),'') for i in range(safe(node.get_n_actions,0) or 0)],
  'children':safe(node.get_child_count,0) or 0,
  'extents':None if box is None else [box.x,box.y,box.width,box.height],
  'focused':bool(states and states.contains(Atspi.StateType.FOCUSED))}
deadline=time.monotonic()+20
while time.monotonic()<deadline:
 values=nodes()
 if values:break
 time.sleep(.2)
else:raise SystemExit('LLM Manager accessibility tree not found')
if mode=='dump':
 print(json.dumps([describe(x) for x in values if describe(x)['name']],ensure_ascii=False));raise SystemExit
if mode=='raw-click':
 x=int(sys.argv[2]); y=int(sys.argv[3]); ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'raw-click','point':[x,y],'ok':bool(ok)},ensure_ascii=False));raise SystemExit
name=sys.argv[2]; role=sys.argv[3] if len(sys.argv)>3 else None
found=[x for x in values if (safe(x.get_name,'') or '')==name and (role is None or safe(x.get_role_name,'')==role)]
if len(found)!=1:raise SystemExit(json.dumps({'wanted':[name,role],'found':[describe(x) for x in found]},ensure_ascii=False))
node=found[0]
if mode=='action':
 count=safe(node.get_n_actions,0) or 0
 if count<1:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 index=int(sys.argv[4]) if len(sys.argv)>4 else 0
 if index>=count:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 ok=node.do_action(index)
 print(json.dumps({'operation':'action','node':describe(node),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='select':
 index=int(sys.argv[4]); iface=node.get_selection_iface(); ok=iface.select_child(index)
 print(json.dumps({'operation':'select','node':describe(node),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='clear-select':
 iface=node.get_selection_iface()
 if iface is None:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 ok=iface.clear_selection()
 print(json.dumps({'operation':'clear-select','node':describe(node),'ok':bool(ok)},ensure_ascii=False))
elif mode=='focus':
 ok=node.grab_focus()
 print(json.dumps({'operation':'focus','node':describe(node),'ok':bool(ok)},ensure_ascii=False))
elif mode=='parent-select':
 parent=node.get_parent(); iface=parent.get_selection_iface(); index=node.get_index_in_parent()
 if iface is None:raise SystemExit(json.dumps({'node':describe(node),'parent':describe(parent)},ensure_ascii=False))
 ok=iface.select_child(index)
 print(json.dumps({'operation':'parent-select','node':describe(node),'parent':describe(parent),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='value':
 iface=node.get_value_iface()
 if iface is None:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 before=iface.get_current_value(); ok=iface.set_current_value(float(sys.argv[4])); after=iface.get_current_value()
 print(json.dumps({'operation':'value','node':describe(node),'before':before,'after':after,'ok':bool(ok)},ensure_ascii=False))
elif mode=='raw-click':
 x=int(sys.argv[2]); y=int(sys.argv[3]); ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'raw-click','point':[x,y],'ok':bool(ok)},ensure_ascii=False))
elif mode=='click':
 box=node.get_extents(Atspi.CoordType.SCREEN)
 # Qt/AT-SPI on this 125%-scaled Wayland session reports client-local
 # logical extents while generated pointer events use physical coordinates.
 x=386+box.x+max(1,box.width//2); y=251+box.y+max(1,box.height//2)
 ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'click','node':describe(node),'point':[x,y],'ok':bool(ok)},ensure_ascii=False))
else:raise SystemExit('bad mode')
