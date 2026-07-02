from pydantic import BaseModel, ConfigDict #ConfigDict is used to configure the behavior of the pydantic model. It allows you to specify various options such as validation, serialization, and more.

from pydantic import EmailStr

class DocumentResponse(BaseModel): #This is the response model for the document upload endpoint. It defines the structure of the response that will be returned when a document is uploaded.
    id: int
    filename: str
    status: str
    file_size: int
    category: str | None = None

    model_config = ConfigDict(from_attributes=True) #This is used to configure the behavior of the pydantic model. It allows you to specify various options such as validation, serialization, and more. In this case, it is set to from_attributes=True, which means that the model will be populated from the attributes of the object being validated, rather than from a dictionary. This is useful when you want to create a pydantic model from an existing object, such as a SQLAlchemy model instance.

    #in simmple words this is used to create a pydantic model from an existing object, such as a SQLAlchemy model instance. It allows you to easily convert a SQLAlchemy model instance into a pydantic model instance, which can then be used for validation, serialization, and more.

    #other uses of ConfigDict include:
    # - validation: You can use ConfigDict to specify validation rules for your pydantic models, such as required fields, field types, and more.
    # - serialization: You can use ConfigDict to specify how your pydantic models should be serialized, such as whether to include or exclude certain fields, how to handle nested models, and more.
    # - other options: ConfigDict also allows you to specify other options for your pydantic models, such as whether to allow extra fields, whether to use aliases for field names, and more. Overall, ConfigDict is a powerful tool for configuring the behavior of your pydantic models and can help you create more robust and flexible data validation and serialization logic in your applications.

    #Example use cases (code):
    #1. Validation:
    #from pydantic import BaseModel, ConfigDict
    #class User(BaseModel):
    #    name: str
    #    age: int
    #    model_config = ConfigDict(extra="forbid") # This will forbid any extra fields that are not defined in the model.
    #user = User(name="Alice", age=30, email="alice@example.com") # This will raise a validation error because the email field is not defined in the model.

    #2. Serialization:
    #from pydantic import BaseModel, ConfigDict
    #class User(BaseModel):
    #    name: str
    #    age: int
    #    email: str
    #    model_config = ConfigDict(include={"name", "age"}) # This will include only the name and age fields when serializing the model.
    #user = User(name="Alice", age=30, email="alice@example.com") # This will include only the name and age fields when serializing the model.


class DocumentStatusUpdate(BaseModel):
    status: str


class ChatRequest(BaseModel):
    question: str
    document_id: int | None = None
    category: str | None = None
    top_k: int = 5


class ChatCitation(BaseModel):
    document_id: int
    chunk_index: int
    score: float
    content_preview: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation]

    
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

    