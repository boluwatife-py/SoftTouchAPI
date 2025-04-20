from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any
import uuid

class ApiParam(BaseModel):
    name: str
    type: str
    description: str

class ApiEndpointSchema(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    method: str
    endpoint: str
    response_type: str
    part_description: str
    description: str
    params: List[ApiParam]
    sample_request: Optional[Any] = None
    sample_response: Optional[Any] = None
    enabled: bool = True
    is_visible_in_stats: bool = True

class ApiStatSchema(BaseModel):
    name: str
    dailyRequests: int = Field(alias='daily_requests')
    weeklyRequests: int = Field(alias='weekly_requests')
    monthlyRequests: int = Field(alias='monthly_requests')
    averageResponseTime: float = Field(alias='average_response_time')
    successRate: float = Field(alias='success_rate')
    popularity: float

class StatisticsSchema(BaseModel):
    totalRequests: int = Field(alias='total_requests')
    uniqueUsers: int = Field(alias='unique_users')
    timestamp: str
    apis: List[ApiStatSchema]

class InsertUser(BaseModel):
    username: str
    password: str

class ContactForm(BaseModel):
    name: str
    email: EmailStr
    message: str
    subject: str