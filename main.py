from dotenv import load_dotenv
load_dotenv()

from api.context import persona
from api.server import app

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 {persona.name} is waking up... Neural Link active on port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
