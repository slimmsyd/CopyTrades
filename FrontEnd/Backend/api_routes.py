from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
from pathlib import Path

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Endpoint(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class EndpointList(BaseModel):
    endpoints: List[Endpoint]

class WalletTrackRequest(BaseModel):
    address: str

def load_endpoints():
    """Load API endpoints from JSON file"""
    try:
        endpoints_file = Path(__file__).parent / 'api_endpoints.json'
        with open(endpoints_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading endpoints: {e}")
        return {"endpoints": []}

def save_endpoints(endpoints: dict) -> bool:
    """Save API endpoints to JSON file"""
    try:
        endpoints_file = Path(__file__).parent / 'api_endpoints.json'
        with open(endpoints_file, 'w') as f:
            json.dump(endpoints, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving endpoints: {e}")
        return False

@app.get("/api/endpoints")
async def get_endpoints():
    """Get all API endpoints"""
    try:
        endpoints = load_endpoints()
        return endpoints
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/endpoints")
async def update_endpoints(endpoints: EndpointList):
    """Update API endpoints"""
    try:
        if save_endpoints(endpoints.dict()):
            return {"message": "Endpoints updated successfully"}
        raise HTTPException(status_code=500, detail="Failed to save endpoints")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: str):
    """Get a specific API endpoint"""
    try:
        endpoints = load_endpoints()
        endpoint = next((e for e in endpoints["endpoints"] if e["id"] == endpoint_id), None)
        if endpoint:
            return endpoint
        raise HTTPException(status_code=404, detail="Endpoint not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/endpoints/{endpoint_id}")
async def update_endpoint(endpoint_id: str, endpoint_data: Endpoint):
    """Update a specific API endpoint"""
    try:
        endpoints = load_endpoints()
        
        for i, endpoint in enumerate(endpoints["endpoints"]):
            if endpoint["id"] == endpoint_id:
                endpoints["endpoints"][i] = endpoint_data.dict()
                if save_endpoints(endpoints):
                    return {"message": "Endpoint updated successfully"}
                raise HTTPException(status_code=500, detail="Failed to save endpoint")
                
        raise HTTPException(status_code=404, detail="Endpoint not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str):
    """Delete a specific API endpoint"""
    try:
        endpoints = load_endpoints()
        original_length = len(endpoints["endpoints"])
        
        endpoints["endpoints"] = [e for e in endpoints["endpoints"] if e["id"] != endpoint_id]
        
        if len(endpoints["endpoints"]) == original_length:
            raise HTTPException(status_code=404, detail="Endpoint not found")
            
        if save_endpoints(endpoints):
            return {"message": "Endpoint deleted successfully"}
        raise HTTPException(status_code=500, detail="Failed to delete endpoint")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/track-wallet")
async def track_wallet(request: WalletTrackRequest):
    """Track a wallet address"""
    try:
        # Validate the wallet address (you may want to add more validation)
        if not request.address or len(request.address) < 32:
            raise HTTPException(status_code=400, detail="Invalid wallet address")
            
        # Here you would typically start your wallet tracking logic
        # For now, we'll just return success
        return {
            "status": "success",
            "message": f"Now tracking wallet: {request.address}",
            "address": request.address
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
