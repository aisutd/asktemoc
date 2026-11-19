from pydantic import BaseModel
from typing import List, Dict, Union

class QueryResponse(BaseModel):
    answer: str
    # sources: List[Union[str, Dict]]