from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from typing import List
import subprocess
import sys
import os
import json
from typing import Optional

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class WalletRequest(BaseModel):
    address: str

# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.tracked_wallets: dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New connection accepted. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            # Remove websocket from tracked wallets
            for wallet in self.tracked_wallets:
                if websocket in self.tracked_wallets[wallet]:
                    self.tracked_wallets[wallet].remove(websocket)
            print(f"Connection removed. Total connections: {len(self.active_connections)}")

    def track_wallet(self, wallet_address: str, websocket: WebSocket = None):
        if wallet_address not in self.tracked_wallets:
            self.tracked_wallets[wallet_address] = []
        if websocket and websocket not in self.tracked_wallets[wallet_address]:
            self.tracked_wallets[wallet_address].append(websocket)
            print(f"Tracking wallet {wallet_address}. Total subscribers: {len(self.tracked_wallets[wallet_address])}")

    async def broadcast_to_wallet(self, wallet_address: str, message: dict):
        """Broadcast message to all subscribers of a specific wallet"""
        if wallet_address not in self.tracked_wallets:
            return
        
        disconnected = []
        for connection in self.tracked_wallets[wallet_address]:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to connection: {str(e)}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error broadcasting to connection: {str(e)}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

# Initialize the connection manager
manager = ConnectionManager()

@app.get("/api/trades")
async def get_trades():
    """Get all tracked trades"""
    try:
        trades_file = os.path.join(os.path.dirname(__file__), "tracked_trades.json")
        print(f"Loading trades from: {trades_file}")
        
        if not os.path.exists(trades_file):
            print("Trades file does not exist yet")
            return {"trades": []}
            
        with open(trades_file, 'r') as f:
            trades = json.load(f)
            print(f"Loaded {len(trades)} trades from file")
            
        # Transform trades to match frontend expected format
        transformed_trades = {}
        for trade_id, trade in trades.items():
            # Get token amount and amount in SOL directly from trade data
            token_amount = float(trade.get('token_amount', 0))
            amount_in_sol = float(trade.get('amount_in_sol', 0))
            
            # Get prices directly from trade data
            buy_price = float(trade.get('buy_price', 0))
            current_price = float(trade.get('current_price', 0))
            profit = float(trade.get('profit', 0))
            profit_percentage = float(trade.get('profit_percentage', 0))
            
            transformed_trades[trade_id] = {
                "id": trade["id"],
                "date_time": trade["date_time"],
                "token_address": trade["token_address"],
                "type": trade.get("type") or trade.get("trade_type"),  # Handle both type and trade_type
                "transaction_link": trade["transaction_link"],
                "result": trade.get("result", "success"),
                "amount_in_sol": amount_in_sol,
                "token_amount": token_amount,
                "wallet_group": trade["wallet_group"],
                "status": trade.get("status", "active"),
                "buy_price": buy_price,
                "current_price": current_price,
                "profit": profit,
                "profit_percentage": profit_percentage
            }
            print(f"Transformed trade {trade_id}:")
            print(f"  Wallet: {trade['wallet_group']}")
            print(f"  Type: {transformed_trades[trade_id]['type']}")
            print(f"  Amount in SOL: {amount_in_sol}")
            print(f"  Token amount: {token_amount}")
            print(f"  Buy price: {buy_price}")
            print(f"  Current price: {current_price}")
            print(f"  Profit: {profit}")
            print(f"  Profit %: {profit_percentage}")
            
        print(f"Returning {len(transformed_trades)} transformed trades")
        return transformed_trades
    except Exception as e:
        print(f"Error loading trades: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/track-wallet")
async def track_wallet(request: WalletRequest):
    """Start tracking a wallet"""
    try:
        # Start wallet tracking script
        script_path = os.path.join(os.path.dirname(__file__), "wallet_tracking.py")
        subprocess.Popen([
            sys.executable,
            script_path,
            "--wallet",
            request.address
        ])
        
        # Add wallet to tracked wallets
        manager.track_wallet(request.address)
        
        return {"status": "success", "message": f"Now tracking wallet: {request.address}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/trades/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                # Receive and parse the message
                data = await websocket.receive_json()
                
                # Handle subscription to wallet
                if "subscribe" in data:
                    wallet_address = data["subscribe"]
                    manager.track_wallet(wallet_address, websocket)
                    await websocket.send_json({
                        "type": "subscription",
                        "status": "success",
                        "wallet": wallet_address
                    })
                
            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
            except ValueError as e:
                # Handle invalid JSON
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid message format"
                })
            except Exception as e:
                print(f"Error in websocket handler: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Internal server error"
                })
    except Exception as e:
        print(f"WebSocket connection error: {str(e)}")
        manager.disconnect(websocket)

# Your existing routes here...

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 