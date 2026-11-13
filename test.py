from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights

res = search_flights("Plan a 7 days Japan trip from India")
print(res)



# res = tavily_search("Best travel destinations in Europe")
# print(res)
