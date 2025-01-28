from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature
import os
import sys
import json
import time
import asyncio
import aiohttp
import websockets
from colorama import init, Fore, Back, Style
import argparse
from typing import Optional, List, Dict, Any, Callable, Union
from datetime import datetime
from constants import *
from websockets.client import connect
from websockets.exceptions import WebSocketException, ConnectionClosedError
from websockets.legacy.protocol import WebSocketCommonProtocol

# Initialize colorama
init(autoreset=True)

# Store connected WebSocket clients
connected_clients = set()

async def handle_client_connection(websocket, path):
    """Handle WebSocket connections from frontend clients"""
    try:
        # Add client to connected clients set
        connected_clients.add(websocket)
        log_info(f"New client connected. Total clients: {len(connected_clients)}")
        
        # Keep connection alive and handle client messages
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'subscribe' and data.get('wallet'):
                    # Handle subscription request
                    log_info(f"Client subscribed to wallet: {data['wallet']}")
            except json.JSONDecodeError:
                log_error(f"Invalid message format from client: {message}")
                
    except websockets.exceptions.ConnectionClosed:
        log_info("Client connection closed")
    finally:
        # Remove client from connected clients set
        connected_clients.remove(websocket)
        log_info(f"Client disconnected. Total clients: {len(connected_clients)}")

async def broadcast_to_clients(message: dict):
    """Broadcast message to all connected clients"""
    if connected_clients:
        websockets_tasks = []
        for client in connected_clients:
            try:
                websockets_tasks.append(
                    asyncio.create_task(client.send(json.dumps(message)))
                )
            except websockets.exceptions.ConnectionClosed:
                continue
        
        if websockets_tasks:
            await asyncio.gather(*websockets_tasks, return_exceptions=True)

def log_info(msg: str):
    """Print info message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.CYAN}[{timestamp}] ℹ {Style.RESET_ALL}{msg}")

def log_success(msg: str):
    """Print success message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.GREEN}[{timestamp}] ✓ {Style.RESET_ALL}{msg}")

def log_warning(msg: str):
    """Print warning message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.YELLOW}[{timestamp}] ⚠ {Style.RESET_ALL}{msg}")

def log_error(msg: str):
    """Print error message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Fore.RED}[{timestamp}] ✖ {Style.RESET_ALL}{msg}")

def log_debug(msg: str):
    """Print debug message with timestamp"""
    if os.getenv('DEBUG'):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{Fore.MAGENTA}[{timestamp}] 🔍 {Style.RESET_ALL}{msg}")

# Constants
HELIUS_API_KEY = "10fc4931-f192-4403-ab41-808bf0b80a67"

# Constants for token classification
SOL_ADDRESS = "So11111111111111111111111111111111111111112"
STABLECOINS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL",
}

def is_sol(mint: str) -> bool:
    """Check if token is SOL"""
    return mint.lower() == SOL_ADDRESS.lower()

def is_stablecoin(mint: str) -> bool:
    """Check if token is a stablecoin"""
    return mint.upper() in [addr.upper() for addr in STABLECOINS.keys()]

def is_sol_or_stable(mint: str) -> bool:
    """Check if token is SOL or a stablecoin"""
    return is_sol(mint) or is_stablecoin(mint)

def get_token_symbol(mint: str) -> str:
    """Get token symbol from mint address"""
    if is_sol(mint):
        return 'SOL'
    return STABLECOINS.get(mint, mint[:4] + '...' + mint[-4:])

import time
from functools import wraps

def rate_limit(calls: int, period: float):
    """Rate limiting decorator"""
    min_interval = period / calls
    last_called = [0.0]  # List to store last call time

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            elapsed = now - last_called[0]
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                await asyncio.sleep(sleep_time)
            
            try:
                result = await func(*args, **kwargs)
                last_called[0] = time.time()
                return result
            except Exception as e:
                if "429" in str(e):  # Rate limit error
                    log_warning("Rate limit hit, waiting before retry...")
                    await asyncio.sleep(1)  # Wait 1 second before retry
                    return await wrapper(*args, **kwargs)
                raise
        return wrapper
    return decorator

# Update RPC endpoints to use Helius
RPC_ENDPOINTS = [
    f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
    "https://api.mainnet-beta.solana.com",  # Fallback
]

class RPCClient:
    def __init__(self, endpoint: str = RPC_ENDPOINTS[0]):
        self.current_endpoint_index = 0
        self.endpoints = RPC_ENDPOINTS
        self.session = None
        self.failed_endpoints = set()
        self.endpoint = endpoint

    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def rotate_endpoint(self):
        """Rotate to next working RPC endpoint"""
        self.current_endpoint_index = (self.current_endpoint_index + 1) % len(self.endpoints)
        self.endpoint = self.endpoints[self.current_endpoint_index]
        log_info(f"Rotated to endpoint: {self.endpoint}")

    async def make_request(self, method: str, params: list) -> Optional[Dict]:
        """Make RPC request with retries"""
        await self.ensure_session()
        
        for _ in range(3):  # Try up to 3 times
            try:
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params
                }
                
                async with self.session.post(self.endpoint, json=request, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "error" in result:
                            log_error(f"RPC error: {result['error']}")
                            await self.rotate_endpoint()
                            continue
                        return result
                    else:
                        log_error(f"HTTP error {response.status}: {await response.text()}")
                        await self.rotate_endpoint()
                        
            except Exception as e:
                log_error(f"Request error: {e}")
                await self.rotate_endpoint()
                
        return None

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_signatures(self, pubkey: str, limit: int = 5) -> List[str]:
        """Get signatures with retries and endpoint rotation"""
        result = await self.make_request(
            "getSignaturesForAddress",
            [pubkey, {"limit": limit}]
        )
        if result and "result" in result:
            return [tx["signature"] for tx in result["result"]]
        return []

    async def get_transaction(self, signature: str) -> Optional[Dict]:
        """Get transaction details"""
        result = await self.make_request(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
        )
        if result and "result" in result:
            return result["result"]
        return None

async def get_signatures_for_address(rpc_client: RPCClient, address: str, limit: int = 1) -> List[str]:
    """Get recent transaction signatures for an address"""
    try:
        signatures = await rpc_client.get_signatures(address, limit)
        return signatures
        
    except Exception as e:
        log_error(f"Error getting signatures: {e}")
        return []

async def handle_account_update(msg):
    """Handle account update message from WebSocket"""
    try:
        if not isinstance(msg, dict):
            log_error("Invalid message format")
            return
            
        # Get transaction info
        tx = msg.get('transaction')
        if not tx or not tx.get('meta'):
            return
            
        signature = msg.get('signature')
        if not signature:
            return
            
        log_info(f"\nNew transaction detected: {signature}")
        
        # Skip failed transactions
        if tx['meta'].get('err'):
            log_warning("Transaction failed, skipping...")
            return
            
        # Get pre and post balances
        pre_balances = tx['meta'].get('preTokenBalances', [])
        post_balances = tx['meta'].get('postTokenBalances', [])
        
        if not pre_balances or not post_balances:
            return
            
        # Calculate balance changes for each token
        changes = []
        for post in post_balances:
            pre = next((p for p in pre_balances 
                       if p['accountIndex'] == post['accountIndex'] 
                       and p['mint'] == post['mint']), None)
                       
            if not pre:
                continue
                
            pre_amount = float(pre['uiTokenAmount'].get('uiAmount', 0) or 0)
            post_amount = float(post['uiTokenAmount'].get('uiAmount', 0) or 0)
            diff = post_amount - pre_amount
            
            if abs(diff) < 0.000001:  # Filter out dust
                continue
                
            changes.append({
                'mint': post['mint'],
                'amount': abs(diff),
                'direction': 'in' if diff > 0 else 'out'
            })
            
        if len(changes) < 2:
            return
            
        # Sort changes by amount (largest first)
        changes.sort(key=lambda x: x['amount'], reverse=True)
        
        # Look for pairs of token movements
        swaps = []
        i = 0
        while i < len(changes) - 1:
            current = changes[i]
            next_change = changes[i + 1]
            
            current_is_sol_stable = is_sol_or_stable(current['mint'])
            next_is_sol_stable = is_sol_or_stable(next_change['mint'])
            
            # One token must be SOL/stable and other must not be
            if current_is_sol_stable != next_is_sol_stable:
                if current['direction'] == 'out' and next_change['direction'] == 'in':
                    swaps.append({
                        'fromMint': current['mint'],
                        'toMint': next_change['mint'],
                        'fromAmount': current['amount'],
                        'toAmount': next_change['amount']
                    })
                elif current['direction'] == 'in' and next_change['direction'] == 'out':
                    swaps.append({
                        'fromMint': next_change['mint'],
                        'toMint': current['mint'],
                        'fromAmount': next_change['amount'],
                        'toAmount': current['amount']
                    })
                i += 2
            else:
                i += 1
                
        if not swaps:
            return
            
        # Get most significant swap
        significant_swap = max(swaps, key=lambda swap: max(swap['fromAmount'], swap['toAmount']))
        
        # Classify trade type
        from_is_sol_or_stable = is_sol_or_stable(significant_swap['fromMint'])
        to_is_sol_or_stable = is_sol_or_stable(significant_swap['toMint'])
        
        trade = None
        
        # If sending SOL/stable and receiving token = BUY
        if from_is_sol_or_stable and not to_is_sol_or_stable:
            trade = {
                'type': 'buy',
                'token_address': significant_swap['toMint'],
                'value': significant_swap['fromAmount'],
                'token_amount': significant_swap['toAmount'],
                'signature': signature,
                'timestamp': int(time.time())
            }
            
        # If sending token and receiving SOL/stable = SELL
        elif not from_is_sol_or_stable and to_is_sol_or_stable:
            trade = {
                'type': 'sell',
                'token_address': significant_swap['fromMint'],
                'value': significant_swap['toAmount'],
                'token_amount': significant_swap['fromAmount'],
                'signature': signature,
                'timestamp': int(time.time())
            }
            
        if trade:
            await on_trade(trade)
            
            # NEW: Track positions
            token_address = significant_swap['toMint'] if trade['type'] == 'buy' else significant_swap['fromMint']
            amount = significant_swap['toAmount'] if trade['type'] == 'buy' else significant_swap['fromAmount']
            
            # Get existing position
            position = tracking_manager.get_position(wallet_address, token_address)
            
            if trade['type'] == 'buy':
                # Add to position
                new_position = position + amount
                tracking_manager.update_position(wallet_address, token_address, new_position)
                log_info(f"{Fore.BLUE}🛒 BUY: {trade['token_amount']} {token_address} "
                        f"for {trade['value']} SOL{Style.RESET_ALL}")
            else:
                # Subtract from position and detect closes
                new_position = position - amount
                if new_position <= 0:
                    # Find and close the oldest open trade for this token
                    open_trades = tracking_manager.get_open_trades(wallet_address, token_address)
                    for trade in open_trades:
                        if trade['token_amount'] <= amount:
                            tracking_manager.close_tracked_trade(trade['id'], significant_swap['price'])
                            amount -= trade['token_amount']
                        else:
                            # Handle partial close
                            tracking_manager.create_partial_close(trade['id'], amount, significant_swap['price'])
                            break
                tracking_manager.update_position(wallet_address, token_address, new_position)
            
            if trade['type'] == 'sell':
                # Get all open positions for this token
                open_trades = tracking_manager.get_open_trades(wallet_address, token_address)
                
                if not open_trades:
                    log_warning(f"No open trades to match sell of {amount} {token_address}")
                    return
                
                # Match using FIFO
                matched = tracking_manager.close_tracked_trade(
                    wallet=wallet_address,
                    token=token_address,
                    sell_amount=amount,
                    sell_price=significant_swap['price']
                )
                
                if matched:
                    log_info(f"{Fore.GREEN}📊 Matched {len(matched)} trades for this sale{Style.RESET_ALL}")
            
            # Calculate actual price
            if from_is_sol_or_stable:
                price = significant_swap['fromAmount'] / significant_swap['toAmount']
            else:
                price = significant_swap['toAmount'] / significant_swap['fromAmount']
            
            # Add to trade data
            trade['price'] = price
            
            await on_trade(trade)
            
    except Exception as e:
        log_error(f"Error handling account update: {str(e)}")
        import traceback
        traceback.print_exc()

from datetime import datetime, timezone
import time

def format_time_ago(timestamp):
    """Format timestamp as time ago"""
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return f"{int(diff)}s ago"
    elif diff < 3600:
        return f"{int(diff/60)}m ago"
    elif diff < 86400:
        return f"{int(diff/3600)}h ago"
    else:
        return f"{int(diff/86400)}d ago"

def format_address(address):
    """Format address to show first and last 4 chars"""
    if not address:
        return "Unknown"
    return f"{address[:4]}...{address[-4:]}"

def format_value(value):
    """Format USD value with appropriate precision"""
    if value >= 1000:
        return f"${value:,.0f}"
    elif value >= 100:
        return f"${value:.1f}"
    else:
        return f"${value:.2f}"

async def get_sol_price() -> float:
    """Fetch current SOL price from CoinGecko API"""
    try:
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0'  # Adding user agent to avoid some rate limits
        }
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            async with session.get(url, headers=headers) as response:
                log_debug(f"CoinGecko API Response Status: {response.status}")
                
                if response.status == 429:  # Rate limit
                    log_warning("CoinGecko rate limit hit, using fallback price")
                    return 100.0
                    
                if response.status != 200:
                    log_warning(f"CoinGecko API returned status {response.status}, using fallback price")
                    return 100.0
                
                try:
                    data = await response.json()
                    log_debug(f"CoinGecko API Response: {data}")
                    
                    if not data or 'solana' not in data or 'usd' not in data['solana']:
                        log_warning("Invalid response format from CoinGecko API")
                        return 100.0
                        
                    price = float(data['solana']['usd'])
                    log_debug(f"Successfully fetched SOL price: ${price}")
                    return price
                    
                except (ValueError, KeyError) as e:
                    log_error(f"Error parsing CoinGecko response: {e}")
                    return 100.0
                    
    except asyncio.TimeoutError:
        log_warning("CoinGecko API request timed out")
        return 100.0
    except Exception as e:
        log_error(f"Unexpected error fetching SOL price: {str(e)}")
        return 100.0  # Fallback price if API call fails

async def track_wallet(wallet_address: str, on_trade: Callable[[Dict[str, Any]], None]):
    """
    Track a wallet's trades in real-time
    
    Args:
        wallet_address: The wallet address to track
        on_trade: Callback function that receives trade details
    """
    rpc_client = RPCClient()
    ws_url = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    last_signature = None
    retry_count = 0
    processed_sigs = set()  # Keep track of processed signatures
    
    while True:  # Keep trying to reconnect
        try:
            # Get initial signature
            initial_sigs = await get_signatures_for_address(rpc_client, wallet_address, 1)
            if initial_sigs:
                last_signature = initial_sigs[0]
                processed_sigs.add(last_signature)
                log_info(f"Starting tracking: {format_address(wallet_address)}")
            
            async with websockets.connect(ws_url) as websocket:
                # Subscribe to account notifications
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "accountSubscribe",
                    "params": [
                        wallet_address,
                        {"encoding": "jsonParsed", "commitment": "finalized"}
                    ]
                }
                
                await websocket.send(json.dumps(subscribe_msg))
                response = await websocket.recv()
                log_info(f"Subscription response: {response}")
                
                while True:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        
                        if "params" in data:
                            # Get latest transactions
                            sigs = await get_signatures_for_address(rpc_client, wallet_address, 10)
                            
                            if sigs:
                                # Process new signatures
                                new_sigs = [sig for sig in sigs if sig not in processed_sigs]
                                
                                if new_sigs:
                                    log_info(f"Found {len(new_sigs)} new transactions")
                                    
                                    for sig in new_sigs:
                                        try:
                                            log_info(f"\nProcessing transaction {sig}")
                                            log_info(f"Wallet address: {wallet_address}")
                                            tx = await rpc_client.get_transaction(sig)
                                            #
                                            
                                            if tx is None:
                                                log_warning(f"Transaction {sig} not found")
                                                continue

                                            log_info("Parsing transaction route...")
                                            route = await parse_route(tx)
                                            
                                            if route and route['type'] in ['buy', 'sell']:
                                                log_info(f"Found {route['type']} trade in tx {sig}")
                                                
                                                # Add transaction signature and wallet group
                                                route['signature'] = sig
                                                route['wallet_group'] = wallet_address
                                                route['date_time'] = datetime.now().isoformat()
                                                
                                                log_info("Calling trade handler...")
                                                # Call the trade handler
                                                if on_trade:
                                                    await on_trade(route)
                                                
                                                # Print transaction details
                                                await print_transaction(sig, route, tx.get('blockTime'))
                                            else:
                                                log_info("No trade found in transaction")
                                            
                                        except Exception as e:
                                            log_error(f"Error processing transaction {sig}: {str(e)}")
                                            import traceback
                                            traceback.print_exc()  # Print full stack trace for debugging
                                            
                                        processed_sigs.add(sig)
                                        
                                        # Keep processed signatures list manageable
                                        if len(processed_sigs) > 1000:
                                            processed_sigs.clear()
                                            processed_sigs.add(sig)
                                
                                last_signature = sigs[0]
                                
                    except (websockets.exceptions.ConnectionClosed, 
                            websockets.exceptions.ConnectionClosedError):
                        log_warning("WebSocket connection closed, reconnecting...")
                        break
                        
                    except Exception as e:
                        log_error(f"Error in WebSocket loop: {str(e)}")
                        import traceback
                        traceback.print_exc()  # Print full stack trace for debugging
                        continue
                        
        except Exception as e:
            retry_count += 1
            wait_time = min(retry_count * 5, 30)  # Exponential backoff
            log_error(f"Connection error (retry {retry_count}): {str(e)}")
            import traceback
            traceback.print_exc()  # Print full stack trace for debugging
            await asyncio.sleep(wait_time)
            continue

async def parse_route(tx: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if not tx.get('meta', {}).get('innerInstructions'):
            log_debug('No inner instructions found')
            return {
                'html': '<span class="text-gray-500">No route</span>', 
                'type': None, 
                'value': 0, 
                'token_address': None,
                'token_amount': 0,
                'amount_in_sol': 0
            }

        log_debug(f"Processing transaction balances:")
        log_debug(f"Pre balances: {json.dumps(tx.get('meta', {}).get('preTokenBalances'), indent=2)}")
        log_debug(f"Post balances: {json.dumps(tx.get('meta', {}).get('postTokenBalances'), indent=2)}")
        
        swaps = []
        pre_balances = tx.get('meta', {}).get('preTokenBalances', [])
        post_balances = tx.get('meta', {}).get('postTokenBalances', [])
        balances_by_owner = {}

        log_debug("Analyzing balance changes...")
        for post in post_balances:
            pre = next((p for p in pre_balances 
                       if p['accountIndex'] == post['accountIndex'] 
                       and p['mint'] == post['mint']), None)

            if pre:
                pre_amount = float(pre.get('uiTokenAmount', {}).get('uiAmount', 0) or 0)
                post_amount = float(post.get('uiTokenAmount', {}).get('uiAmount', 0) or 0)
                diff = post_amount - pre_amount
                owner = post.get('owner')

                if owner not in balances_by_owner:
                    balances_by_owner[owner] = []

                if abs(diff) > 0.001:
                    balances_by_owner[owner].append({
                        'mint': post['mint'],
                        'amount': abs(diff),
                        'direction': 'in' if diff > 0 else 'out'
                    })
                    log_debug(f"Found balance change for {post['mint']}: {diff} ({pre_amount} -> {post_amount})")

        max_changes = 0
        main_owner = None
        for owner, owner_changes in balances_by_owner.items():
            if len(owner_changes) > max_changes:
                max_changes = len(owner_changes)
                main_owner = owner

        if not main_owner:
            log_debug('No significant changes found')
            return {
                'html': '<span class="text-gray-500">No route</span>', 
                'type': None, 
                'value': 0, 
                'token_address': None,
                'token_amount': 0,
                'amount_in_sol': 0
            }

        log_debug(f"Main owner found: {main_owner}")
        main_owner_changes = balances_by_owner[main_owner]
        main_owner_changes.sort(key=lambda x: x['amount'], reverse=True)

        log_debug("Looking for swaps...")
        i = 0
        while i < len(main_owner_changes) - 1:
            current = main_owner_changes[i]
            next_change = main_owner_changes[i + 1]

            current_is_sol_or_stable = is_sol_or_stable(current['mint'])
            next_is_sol_or_stable = is_sol_or_stable(next_change['mint'])

            if current_is_sol_or_stable != next_is_sol_or_stable:
                if current['direction'] == 'out' and next_change['direction'] == 'in':
                    log_debug(f"Found swap: {current['mint']} -> {next_change['mint']}")
                    swaps.append({
                        'fromMint': current['mint'],
                        'toMint': next_change['mint'],
                        'fromAmount': float(current['amount']),
                        'toAmount': float(next_change['amount'])
                    })
                elif current['direction'] == 'in' and next_change['direction'] == 'out':
                    log_debug(f"Found swap: {next_change['mint']} -> {current['mint']}")
                    swaps.append({
                        'fromMint': next_change['mint'],
                        'toMint': current['mint'],
                        'fromAmount': float(next_change['amount']),
                        'toAmount': float(current['amount'])
                    })
                i += 2
            else:
                i += 1

        if not swaps:
            log_debug('No swaps found')
            return {
                'html': '<span class="text-gray-500">No route</span>', 
                'type': None, 
                'value': 0, 
                'token_address': None,
                'token_amount': 0,
                'amount_in_sol': 0
            }

        significant_swap = max(swaps, key=lambda swap: max(swap['fromAmount'], swap['toAmount']))

        from_is_sol_or_stable = is_sol_or_stable(significant_swap['fromMint'])
        to_is_sol_or_stable = is_sol_or_stable(significant_swap['toMint'])

        print("\n=== Analyzing Trade ===")
        # What he Bought/Sold
        print(f"From token: {significant_swap['fromMint']} ({get_token_symbol(significant_swap['fromMint'])})")
        print(f"To token: {significant_swap['toMint']} ({get_token_symbol(significant_swap['toMint'])})")
        
        # Amount details
        print(f"From amount: {significant_swap['fromAmount']:,.4f}")
        print(f"To amount: {significant_swap['toAmount']:,.4f}")
        
        # If the to_token is SOL, calculate USD value using live price
        sol_price = await get_sol_price()
        if is_sol(significant_swap['toMint']):
            sol_amount = significant_swap['toAmount']
            usd_value = sol_amount * sol_price
            print(f"Approximate USD value: ${usd_value:,.2f} (SOL price: ${sol_price:,.2f})")

        # Classification info
        print(f"Is from SOL/stable: {from_is_sol_or_stable}")
        print(f"Is to SOL/stable: {to_is_sol_or_stable}")

        trade_type = None
        route_html = None
        token_address = None
        token_amount = None
        amount_in_sol = None

        if from_is_sol_or_stable and not to_is_sol_or_stable:
            trade_type = 'buy'
            token_symbol = get_token_symbol(significant_swap['toMint'])
            route_html = f'<span class="text-green-500">{token_symbol}</span>'
            token_address = significant_swap['toMint']
            token_amount = float(significant_swap['toAmount'])
            amount_in_sol = float(significant_swap['fromAmount'])
            
            print(f"\n🟢 BUY Trade Detected:")
            print(f"Token Address: {token_address}")
            print(f"Token Symbol: {token_symbol}")
            print(f"Amount Paid: {amount_in_sol} SOL (${amount_in_sol * sol_price:,.2f})")
            print(f"Tokens Received: {token_amount}")
            
        elif not from_is_sol_or_stable and to_is_sol_or_stable:
            trade_type = 'sell'
            token_symbol = get_token_symbol(significant_swap['fromMint'])
            route_html = f'<span class="text-red-500">{token_symbol}</span>'
            token_address = significant_swap['fromMint']
            token_amount = float(significant_swap['fromAmount'])
            amount_in_sol = float(significant_swap['toAmount'])
            
            print(f"\n🔴 SELL Trade Detected:")
            print(f"Token Address: {token_address}")
            print(f"Token Symbol: {token_symbol}")
            print(f"Tokens Sold: {token_amount}")
            print(f"SOL Received: {amount_in_sol} SOL (${amount_in_sol * sol_price:,.2f})")

        if not trade_type or not route_html:
            log_debug('Could not classify trade type')
            return {
                'html': '<span class="text-gray-500">No route</span>', 
                'type': None, 
                'value': 0, 
                'token_address': None,
                'token_amount': 0,
                'amount_in_sol': 0
            }

        trade_data = {
            'html': route_html,
            'type': trade_type,
            'value': 0,  # Not using this anymore
            'token_address': token_address,
            'token_amount': token_amount,
            'amount_in_sol': amount_in_sol,
            'raw_swap': significant_swap     # Adding raw swap data for debugging
        }
        
        print(f"\nFinal Trade Data:")
        print(json.dumps(trade_data, indent=2))
        
        return trade_data

    except Exception as error:
        log_error(f'Error parsing route: {str(error)}')
        import traceback
        traceback.print_exc()
        return {
            'html': '<span class="text-gray-500">No route</span>', 
            'type': None, 
            'value': 0, 
            'token_address': None,
            'token_amount': 0,
            'amount_in_sol': 0
        }

async def print_transaction(signature: str, route: dict, block_time: Optional[int] = None):
    """Print transaction details in a formatted way"""
    try:
        time_str = format_time_ago(block_time) if block_time else "Unknown time"
        token_symbol = get_token_symbol(route['token_address'])
        wallet_address = route.get('wallet_group', 'Unknown wallet')
        
        # Create a box around the transaction details
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.CYAN}Transaction Details")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        # Print each detail with proper formatting
        print(f"{Fore.WHITE}👛 Wallet:{Style.RESET_ALL} {Fore.YELLOW}{format_address(wallet_address)}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}🔗 Transaction:{Style.RESET_ALL} {Fore.CYAN}{signature}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}⏰ Time:{Style.RESET_ALL} {time_str}")
        
        # Color code the trade type
        type_color = Fore.GREEN if route['type'] == 'buy' else Fore.RED
        print(f"{Fore.WHITE}📊 Type:{Style.RESET_ALL} {type_color}{route['type'].upper()}{Style.RESET_ALL}")
        
        print(f"{Fore.WHITE}🪙 Token:{Style.RESET_ALL} {Fore.YELLOW}{token_symbol}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}💵 Value:{Style.RESET_ALL} ${route['amount_in_sol']:.2f}")
        print(f"{Fore.WHITE}📈 Amount:{Style.RESET_ALL} {route['token_amount']:.6f}")
        
        # Add bottom border
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        # Print transaction URL
        print(f"{Fore.WHITE}🔍 View on Solscan:{Style.RESET_ALL} {Fore.BLUE}https://solscan.io/tx/{signature}{Style.RESET_ALL}\n")
        
    except Exception as e:
        log_error(f"Error printing transaction: {str(e)}")

from get_sell_percentage import analyze_token_transfer

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wallet', type=str, required=True)
    args = parser.parse_args()
    
    log_info("\nWallet Tracking Bot")
    log_info("=====================")
    
    # Initialize tracking manager
    from tracking_manager import TrackingManager
    tracking_manager = TrackingManager()
    
    # Create a single WebSocket connection
    ws = None
    try:
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect('ws://localhost:8000/trades/ws')
            log_info("Connected to WebSocket server")
            
            async def handle_trade(trade):
                """Handle new trade by logging it and broadcasting to clients"""
                try:
                    print("\n=== Starting Trade Handler ===")
                    print("Initial trade data:")
                    print(json.dumps(trade, indent=2))
                    
                    # Extract token amount and amount in SOL
                    token_amount = float(trade.get('token_amount', 0))
                    amount_in_sol = float(trade.get('amount_in_sol', 0))
                    
                    print(f"\nProcessing amounts:")
                    print(f"Token amount: {token_amount}")
                    print(f"Amount in SOL: {amount_in_sol}")
                    
                    # If token amount is 0, try to get it from raw swap data
                    if token_amount == 0 and 'raw_swap' in trade:
                        raw_swap = trade['raw_swap']
                        print("\nToken amount is 0, extracting from raw swap data:")
                        print(json.dumps(raw_swap, indent=2))
                        
                        if trade['type'] == 'buy':
                            token_amount = float(raw_swap.get('toAmount', 0))
                            amount_in_sol = float(raw_swap.get('fromAmount', 0))
                        else:  # sell
                            token_amount = float(raw_swap.get('fromAmount', 0))
                            amount_in_sol = float(raw_swap.get('toAmount', 0))
                            
                        print(f"Recovered amounts from raw swap:")
                        print(f"Token amount: {token_amount}")
                        print(f"Amount in SOL: {amount_in_sol}")
                        
                        # Update trade data with recovered values
                        trade['token_amount'] = token_amount
                        trade['amount_in_sol'] = amount_in_sol
                    
                    # Calculate price per token
                    price_per_token = amount_in_sol / token_amount if token_amount > 0 else 0
                    
                    print("\nPreparing to save trade...")
                    print(f"Token address: {trade['token_address']}")
                    print(f"Trade type: {trade['type']}")
                    print(f"Token amount: {token_amount}")
                    print(f"Amount in SOL: {amount_in_sol}")
                    print(f"Price per token: {price_per_token}")
                    
                    print("\nCalling tracking_manager.add_tracked_trade()...")
                    
                    # Save trade using tracking manager
                    saved_trade = tracking_manager.add_tracked_trade(
                        token_address=trade['token_address'],
                        buy_price=price_per_token if trade['type'] == 'buy' else 0,
                        transaction_link=f"https://solscan.io/tx/{trade['signature']}",
                        amount_in_sol=amount_in_sol,
                        token_amount=token_amount,
                        trade_type=trade['type'],
                        result='success',
                        wallet_group=trade['wallet_group']
                    )
                    
                    print("\nTrade saved successfully!")
                    print(f"Trade ID: {saved_trade['id']}")
                    print(f"Token: {trade['token_address']}")
                    print(f"Amount: {token_amount}")
                    print(f"Price: {price_per_token}")
                    
                    # Broadcast to WebSocket clients
                    if ws and not ws.closed:
                        print("\nBroadcasting trade to WebSocket clients...")
                        await ws.send_json({
                            "type": "trade",
                            "data": {
                                **trade,
                                "price_per_token": price_per_token,
                                "token_amount": token_amount,
                                "amount_in_sol": amount_in_sol
                            }
                        })
                        print("Trade broadcast complete")
                    else:
                        print("WARNING: WebSocket connection is closed, trade not broadcast")
                    
                except Exception as e:
                    print(f"\n❌ Error in handle_trade:")
                    print(str(e))
                    import traceback
                    traceback.print_exc()
            
            # Start wallet tracking
            await track_wallet(args.wallet, handle_trade)
            
    except Exception as e:
        log_error(f"Error in main loop: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if ws and not ws.closed:
            await ws.close()
            log_info("WebSocket connection closed")

if __name__ == "__main__":
    asyncio.run(main())
