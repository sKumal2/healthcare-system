import uuid
class QueryService:
    def processRequest(
        self, 
        conversation_id: str,
        user_id: int,
        organization_id: int,
        query: str,
    ):
        response = "Hello World!"


        return {
            "message_id": str(uuid.uuid4()),
            "response": response,
            "citations": [],
            "tokens_used": 0,
        }

    