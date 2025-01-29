from datetime import datetime, timezone
import json
import os
from typing import Dict, Optional, Any, List
import logging
import time
import fcntl
from natsort import natsorted
from collections import defaultdict
from colorama import Fore, Style, init

init()  # Initialize colorama

class TrackingManager:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        # Initialize logger first
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        # Add a console handler if none exists
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # Use single file in Backend directory
        self.tracked_trades_file = os.path.join(os.path.dirname(__file__), 'tracked_trades.json')
        
        # Load trades after logger is initialized
        self.trades: Dict[str, Any] = self._load_tracked_trades()
        
        self.logger.debug(f"Initialized with {len(self.trades)} trades from {self.tracked_trades_file}")
        
        self.positions = defaultdict(float)  # Key: (wallet, token) -> amount
        self.open_trades = defaultdict(list)  # Key: (wallet, token) -> list of open trades
        self.closed_trades = defaultdict(list)  # Key: (wallet, token) -> list of closed trades
        
        # Load closed trades
        try:
            closed_trades_file = os.path.join(os.path.dirname(__file__), 'closed_trades.json')
            if os.path.exists(closed_trades_file):
                with open(closed_trades_file, 'r') as f:
                    closed_data = json.load(f)
                    # Convert keys from strings to tuples
                    self.closed_trades = defaultdict(list, {
                        (k[0], k[1]): v for k, v in closed_data.items()
                    })
        except Exception as e:
            self.logger.error(f"Error loading closed trades: {str(e)}")
            self.closed_trades = defaultdict(list)

    def _load_tracked_trades(self):
        """Load tracked trades from file with file locking"""
        try:
            if not os.path.exists(self.tracked_trades_file):
                self.logger.debug(f"No existing trades file found at {self.tracked_trades_file}, starting with empty trades")
                return {}

            with open(self.tracked_trades_file, 'r') as f:
                # Get exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    trades = json.load(f)
                    self.logger.debug(f"Loaded {len(trades)} trades from {self.tracked_trades_file}")
                    self.logger.debug(f"Latest trade IDs: {sorted(list(trades.keys()))[-5:] if trades else []}")
                    return trades
                finally:
                    # Release lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            self.logger.error(f"Error loading tracked trades from {self.tracked_trades_file}: {str(e)}")
            return {}

    def _get_next_trade_id(self):
        """Get the next available trade ID"""
        try:
            existing_trades = self._load_tracked_trades()
            if not existing_trades:
                return "tracked_trade_1"
                
            # Extract numbers from both formats of trade IDs
            existing_numbers = []
            for trade_id in existing_trades.keys():
                if trade_id.startswith('tracked_trade_'):
                    num = int(trade_id.replace("tracked_trade_", ""))
                    existing_numbers.append(num)
                elif trade_id.startswith('trade_'):
                    num = int(trade_id.replace("trade_", ""))
                    # Convert old format number to new format range
                    existing_numbers.append(num + 56)  # Since we have 56 tracked_trade_X entries
            
            next_number = max(existing_numbers) + 1 if existing_numbers else 1
            return f"tracked_trade_{next_number}"
            
        except Exception as e:
            self.logger.error(f"Error generating trade ID: {str(e)}")
            # Fallback to timestamp-based ID if something goes wrong
            return f"tracked_trade_{int(time.time())}"

    def _save_tracked_trades(self):
        """Save tracked trades to file with file locking"""
        try:
            self.logger.debug(f"Starting save process for {len(self.trades)} trades")
            
            # Sort all trades using natural sorting
            trade_ids = natsorted(self.trades.keys())
            sorted_trades = {trade_id: self.trades[trade_id] for trade_id in trade_ids}
            
            self.logger.debug(f"Sorted {len(sorted_trades)} trades")
            
            # Open file in read/write mode to get lock
            with open(self.tracked_trades_file, 'r+' if os.path.exists(self.tracked_trades_file) else 'w+') as f:
                # Get exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    # Read existing trades
                    try:
                        f.seek(0)
                        existing_trades = json.load(f)
                        self.logger.debug(f"Read {len(existing_trades)} existing trades before merge")
                    except (json.JSONDecodeError, ValueError):
                        self.logger.warning("Could not read existing trades, starting fresh")
                        existing_trades = {}
                    
                    # Merge and sort all trades
                    all_trades = {**existing_trades, **sorted_trades}
                    trade_ids = natsorted(all_trades.keys())
                    final_trades = {trade_id: all_trades[trade_id] for trade_id in trade_ids}
                    
                    # Write back
                    f.seek(0)
                    f.truncate()
                    json.dump(final_trades, f, indent=2, default=str)
                    
                    total_trades = len(final_trades)
                    self.logger.debug(f"Successfully saved {total_trades} trades to {self.tracked_trades_file}")
                    
                    # Update our in-memory trades with sorted version
                    self.trades = final_trades
                    
                    # Verify the write
                    f.flush()
                    os.fsync(f.fileno())
                    
                finally:
                    # Release lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
        except Exception as e:
            self.logger.error(f"Error saving trades: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

    def add_tracked_trade(
        self,
        token_address: str,
        buy_price: float,
        transaction_link: str,
        amount_in_sol: float,
        token_amount: float,
        trade_type: str,
        result: str,
        wallet_group: Optional[str] = None
    ) -> Dict:
        """Add a new tracked trade"""
        try:
            print(f"\n{Fore.CYAN}{'='*50}")
            print(f"{Fore.CYAN}Adding New Trade - Detailed Logging{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
            
            # Log initial trade parameters
            print(f"\n{Fore.WHITE}📝 Trade Parameters:{Style.RESET_ALL}")
            print(f"Token: {Fore.YELLOW}{token_address}{Style.RESET_ALL}")
            print(f"Type: {Fore.GREEN if trade_type == 'buy' else Fore.RED}{trade_type}{Style.RESET_ALL}")
            print(f"Amount: {Fore.CYAN}{amount_in_sol} SOL{Style.RESET_ALL}")
            print(f"Token amount: {Fore.CYAN}{token_amount}{Style.RESET_ALL}")
            print(f"Wallet: {Fore.YELLOW}{wallet_group}{Style.RESET_ALL}")
            
            trade_id = self._get_next_trade_id()
            print(f"\n{Fore.GREEN}✓ Generated trade ID: {trade_id}{Style.RESET_ALL}")
            
            # Get current SOL price with enhanced logging
            sol_price = 100.0  # Default fallback price
            try:
                import aiohttp
                import asyncio
                
                async def get_current_sol_price():
                    print(f"\n{Fore.WHITE}📊 Fetching current SOL price...{Style.RESET_ALL}")
                    async with aiohttp.ClientSession() as session:
                        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                price = float(data['solana']['usd'])
                                print(f"{Fore.GREEN}✓ SOL price fetched: ${price}{Style.RESET_ALL}")
                                return price
                    print(f"{Fore.YELLOW}⚠️ Using fallback SOL price: $100{Style.RESET_ALL}")
                    return 100.0  # Fallback price
                
                # Run the async function to get SOL price
                sol_price = asyncio.run(get_current_sol_price())
            except Exception as e:
                self.logger.warning(f"Failed to get SOL price, using fallback: {e}")
                print(f"{Fore.YELLOW}⚠️ Using fallback SOL price due to error: {e}{Style.RESET_ALL}")
            
            # Calculate USD values with logging
            buy_price_usd = buy_price * sol_price
            amount_in_usd = amount_in_sol * sol_price
            
            print(f"\n{Fore.WHITE}💰 USD Calculations:{Style.RESET_ALL}")
            print(f"Buy price (USD): ${buy_price_usd:.4f}")
            print(f"Total amount (USD): ${amount_in_usd:.2f}")
            
            trade = {
                "id": trade_id,
                "date_time": time.strftime('%Y-%m-%dT%H:%M:%S.%f'),
                "token_address": token_address,
                "buy_price": buy_price,
                "buy_price_usd": buy_price_usd,
                "close_price": None,
                "current_price": buy_price,
                "current_price_usd": buy_price_usd,
                "profit": 0.0,
                "profit_percentage": 0.0,
                "status": "active",
                "result": result,
                "transaction_link": transaction_link,
                "amount_in_sol": amount_in_sol,
                "amount_in_usd": amount_in_usd,
                "token_amount": token_amount,
                "wallet_group": wallet_group,
                "trade_type": trade_type,
            }
            
            print(f"\n{Fore.WHITE}📋 Trade Data to Save:{Style.RESET_ALL}")
            print(json.dumps(trade, indent=2))
            
            # Add to our in-memory trades
            self.trades[trade_id] = trade
            
            # Store in open trades
            key = (wallet_group, token_address)
            self.open_trades[key].append(trade)
            
            print(f"\n{Fore.CYAN}💾 Saving to files...{Style.RESET_ALL}")
            # Save to file
            self._save_tracked_trades()
            
            # Verify the save
            print(f"\n{Fore.WHITE}🔍 Verifying save...{Style.RESET_ALL}")
            saved_trades = self._load_tracked_trades()
            if trade_id in saved_trades:
                print(f"{Fore.GREEN}✓ Successfully saved trade {trade_id}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}Total trades in file: {len(saved_trades)}{Style.RESET_ALL}")
                print(f"{Fore.WHITE}Latest trade IDs: {sorted(list(saved_trades.keys()))[-5:]}{Style.RESET_ALL}")
                
                # Verify trade data integrity
                saved_trade = saved_trades[trade_id]
                all_fields_match = all(saved_trade[k] == v for k, v in trade.items())
                if all_fields_match:
                    print(f"{Fore.GREEN}✓ Trade data integrity verified{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}❌ Trade data mismatch detected!{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}❌ Failed to save trade {trade_id}!{Style.RESET_ALL}")
            
            print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
            return trade
            
        except Exception as e:
            print(f"\n{Fore.RED}❌ Error adding trade:")
            print(str(e))
            import traceback
            traceback.print_exc()
            raise

    def _match_trades_fifo(self, wallet: str, token: str, sell_amount: float):
        """Match sells to oldest buys using FIFO accounting"""
        key = (wallet, token)
        remaining = sell_amount
        matched = []

        self.logger.info(f"{Fore.CYAN}⏳ Matching {sell_amount} {token} sells for {wallet}...{Style.RESET_ALL}")

        while remaining > 0 and self.open_trades[key]:
            oldest_trade = self.open_trades[key][0]
            
            if oldest_trade['token_amount'] <= remaining:
                # Full match
                self.logger.info(
                    f"{Fore.GREEN}✅ FULL MATCH: Sold {oldest_trade['token_amount']} {token} "
                    f"bought at {oldest_trade['buy_price']} (ID: {oldest_trade['id']}){Style.RESET_ALL}"
                )
                matched.append({
                    'buy_trade': oldest_trade,
                    'sold_amount': oldest_trade['token_amount']
                })
                remaining -= oldest_trade['token_amount']
                self.open_trades[key].pop(0)
            else:
                # Partial match
                self.logger.info(
                    f"{Fore.YELLOW}⚠️ PARTIAL MATCH: Sold {remaining} of {oldest_trade['token_amount']} {token} "
                    f"bought at {oldest_trade['buy_price']} (ID: {oldest_trade['id']}){Style.RESET_ALL}"
                )
                matched.append({
                    'buy_trade': oldest_trade,
                    'sold_amount': remaining
                })
                oldest_trade['token_amount'] -= remaining
                remaining = 0
                
        if remaining > 0:
            self.logger.error(
                f"{Fore.RED}❌ INSUFFICIENT POSITION: Couldn't match {remaining} {token} sells{Style.RESET_ALL}"
            )

        self._save_open_trades()
        self._save_tracked_trades()
        return matched, remaining

    def get_tracked_trade(self, trade_id: str) -> Optional[Dict]:
        """Get a tracked trade by ID"""
        return self.trades.get(trade_id)

    def update_tracked_trade(self, trade_id: str, updates: Dict) -> Optional[Dict]:
        """Update a tracked trade"""
        if trade_id in self.trades:
            # Get current SOL price
            sol_price = 100.0  # Default fallback price
            try:
                import aiohttp
                import asyncio
                
                async def get_current_sol_price():
                    if self.test_mode:
                        return 100  # Hardcode for tests
                    async with aiohttp.ClientSession() as session:
                        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                return float(data['solana']['usd'])
                    return 100.0  # Fallback price
                
                # Run the async function to get SOL price
                sol_price = asyncio.run(get_current_sol_price())
            except Exception as e:
                self.logger.warning(f"Failed to get SOL price, using fallback: {e}")
            
            # Update USD values if price fields are being updated
            if 'current_price' in updates:
                updates['current_price_usd'] = updates['current_price'] * sol_price
            
            if 'buy_price' in updates:
                updates['buy_price_usd'] = updates['buy_price'] * sol_price
                
            if 'amount_in_sol' in updates:
                updates['amount_in_usd'] = updates['amount_in_sol'] * sol_price
            
            self.trades[trade_id].update(updates)
            self._save_tracked_trades()
            return self.trades[trade_id]
        return None

    def close_tracked_trade(self, wallet: str, token: str, sell_amount: float, sell_price: float):
        """Close trades using FIFO matching with enhanced logging"""
        print(f"\n{Fore.CYAN}{'='*50}")
        print(f"{Fore.CYAN}Closing Trade - Detailed Logging{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        print(f"\n{Fore.WHITE}📝 Close Parameters:{Style.RESET_ALL}")
        print(f"Wallet: {Fore.YELLOW}{wallet}{Style.RESET_ALL}")
        print(f"Token: {Fore.YELLOW}{token}{Style.RESET_ALL}")
        print(f"Sell amount: {Fore.CYAN}{sell_amount}{Style.RESET_ALL}")
        print(f"Sell price: {Fore.CYAN}{sell_price} SOL{Style.RESET_ALL}")
        
        key = (wallet, token)
        matched_trades, remaining = self._match_trades_fifo(wallet, token, sell_amount)
        
        if remaining > 0:
            print(f"\n{Fore.YELLOW}⚠️ Warning: {remaining} tokens couldn't be matched to open trades{Style.RESET_ALL}")
        
        total_profit = 0
        print(f"\n{Fore.WHITE}📊 Processing Matched Trades:{Style.RESET_ALL}")
        
        for match in matched_trades:
            buy_trade = match['buy_trade']
            sold_amount = match['sold_amount']
            profit = (sell_price - buy_trade['buy_price']) * sold_amount
            total_profit += profit
            
            # Calculate profit for this match
            profit_percentage = ((sell_price / buy_trade['buy_price']) - 1) * 100
            
            print(f"\n{Fore.WHITE}Trade {buy_trade['id']}:{Style.RESET_ALL}")
            print(f"Sold amount: {Fore.CYAN}{sold_amount}{Style.RESET_ALL}")
            print(f"Profit: {Fore.GREEN if profit >= 0 else Fore.RED}{profit:.4f} SOL{Style.RESET_ALL}")
            print(f"Profit %: {Fore.GREEN if profit_percentage >= 0 else Fore.RED}{profit_percentage:.2f}%{Style.RESET_ALL}")
            
            # Create closed trade record
            closed_trade = {
                **buy_trade,
                'closed_at': datetime.now().isoformat(),
                'close_price': sell_price,
                'sold_amount': sold_amount,
                'profit': profit,
                'profit_percentage': profit_percentage,
                'status': 'closed' if sold_amount == buy_trade['token_amount'] else 'partial'
            }
            
            if sold_amount < buy_trade['token_amount']:
                print(f"\n{Fore.YELLOW}⚠️ Partial sale detected{Style.RESET_ALL}")
                # Add partial sale record
                if 'partial_sales' not in buy_trade:
                    buy_trade['partial_sales'] = []
                buy_trade['partial_sales'].append({
                    'amount': sold_amount,
                    'price': sell_price,
                    'date_time': datetime.now().isoformat()
                })
                self.update_tracked_trade(buy_trade['id'], buy_trade)
                print(f"{Fore.GREEN}✓ Partial sale recorded{Style.RESET_ALL}")
            
            self.closed_trades[key].append(closed_trade)
            
            # Update the original trade in main trades dict
            self.trades[buy_trade['id']].update({
                "status": "closed" if sold_amount == buy_trade['token_amount'] else "partial",
                "close_price": sell_price,
                "closed_at": datetime.now().isoformat()
            })
            print(f"{Fore.GREEN}✓ Trade {buy_trade['id']} status updated{Style.RESET_ALL}")
        
        print(f"\n{Fore.WHITE}💾 Saving trade data...{Style.RESET_ALL}")
        self._save_closed_trades()
        self._save_tracked_trades()
        
        if matched_trades:
            print(f"\n{Fore.GREEN}💰 TOTAL PROFIT: {total_profit:.4f} SOL{Style.RESET_ALL}")
            sol_price = 100  # You can replace this with actual SOL price if available
            print(f"{Fore.GREEN}💵 Approximate USD value: ${total_profit * sol_price:.2f}{Style.RESET_ALL}")
        
        print(f"\n{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        return matched_trades

    def get_trades(self):
        """Get all tracked trades"""
        return self.trades

    def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        """Update an existing trade"""
        if trade_id in self.trades:
            self.trades[trade_id].update(updates)
            self._save_tracked_trades()
            return True
        return False

    def remove_trade(self, trade_id: str):
        """Remove a trade from tracking"""
        if trade_id in self.trades:
            del self.trades[trade_id]
            self._save_tracked_trades()
            return True
        return False

    def get_position(self, wallet: str, token: str) -> float:
        return self.positions.get((wallet, token), 0.0)
        
    def update_position(self, wallet: str, token: str, amount: float):
        self.positions[(wallet, token)] = amount
        self._save_positions()
        
    def get_open_trades(self, wallet: str, token: str) -> List[Dict]:
        return [t for t in self.trades.values() 
                if t['wallet_group'] == wallet 
                and t['token_address'] == token
                and t['status'] == 'active']

    def _save_open_trades(self):
        """Save open trades structure to file"""
        try:
            open_trades_file = os.path.join(os.path.dirname(__file__), 'open_trades.json')
            with open(open_trades_file, 'w') as f:
                json.dump(self.open_trades, f, indent=2)
            self.logger.debug(f"Saved {len(self.open_trades)} open trade groups")
        except Exception as e:
            self.logger.error(f"Error saving open trades: {str(e)}")

    def _save_closed_trades(self):
        """Create/update closed_trades.json file"""
        try:
            closed_trades_file = os.path.join(os.path.dirname(__file__), 'closed_trades.json')
            with open(closed_trades_file, 'w') as f:
                # Convert tuple keys to strings
                save_data = {
                    str(k): v for k, v in self.closed_trades.items()
                }
                json.dump(save_data, f, indent=2)
            self.logger.info(f"💾 Saved {sum(len(v) for v in self.closed_trades.values())} closed trades")
        except Exception as e:
            self.logger.error(f"Error saving closed trades: {str(e)}")
