from app.services.protective_order_verification import verify_protective_orders
class Adapter:
 def __init__(self,p,o): self.p,self.o=p,o
 def get_positions(self): return self.p
 def get_orders(self): return self.o

def test_uncovered_position_fails_closed():
 r=verify_protective_orders(Adapter([{'symbol':'AAPL','qty':'1'}], []))
 assert not r['protected'] and r['uncovered_positions']==['AAPL']
def test_matching_open_stop_protects_position():
 r=verify_protective_orders(Adapter([{'symbol':'AAPL','qty':'1'}],[{'symbol':'AAPL','type':'stop','status':'accepted'}]))
 assert r['protected']
