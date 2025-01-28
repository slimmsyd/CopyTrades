import asyncio
from tracking_manager import TrackingManager
from datetime import datetime, timedelta

async def main():
    # Initialize with test mode
    tm = TrackingManager()
    tm.logger.disabled = True  # Disable file logging for tests
    
    # Test token details
    test_wallet = "test_wallet_1"
    test_token = "TEST_TOKEN_123"
    
    # Simulate 3 buys
    buy_trades = []
    for i in range(1, 4):
        trade = tm.add_tracked_trade(
            token_address=test_token,
            buy_price=0.1 * i,  # 0.1, 0.2, 0.3 SOL
            transaction_link=f"https://testscan.io/tx/buy_{i}",
            amount_in_sol=10 * i,  # 10, 20, 30 SOL
            token_amount=100 * i,  # 100, 200, 300 tokens
            trade_type='buy',
            wallet_group=test_wallet,
            result='success'
        )
        buy_trades.append(trade)
        print(f"✅ Bought {trade['token_amount']} tokens @ {trade['buy_price']} SOL. ID: {trade['id']}")

    # Verify open trades
    open_trades = tm.get_open_trades(test_wallet, test_token)
    print(f"\n📂 Open trades: {len(open_trades)}")
    
    # Simulate sell that should close first 2 buys and partially close third
    print("\n💸 Simulating sell of 350 tokens...")
    closed_trades = tm.close_tracked_trade(
        wallet=test_wallet,
        token=test_token,
        sell_amount=350,
        sell_price=0.5  # Selling at 0.5 SOL/token
    )
    
    # Verify results
    print("\n🔍 Results:")
    print(f"Closed {len(closed_trades)} trade lots")
    
    # Check remaining open trades
    remaining_open = tm.get_open_trades(test_wallet, test_token)
    print(f"\n📂 Remaining open trades: {len(remaining_open)}")
    if remaining_open:
        print(f"Remaining tokens: {remaining_open[0]['token_amount']} @ {remaining_open[0]['buy_price']} SOL")

    # Verify closed trades
    closed_in_system = [t for t in tm.trades.values() if t['status'] != 'active']
    print(f"\n🔒 Closed trades in system: {len(closed_in_system)}")
    
    # Verify FIFO order
    print("\n🧮 Profit Calculations:")
    total_profit = 0
    for trade in closed_trades:  # Use the directly returned closed trades
        buy_trade = trade['buy_trade']
        profit = (trade['close_price'] - buy_trade['buy_price']) * trade['sold_amount']
        print(f"Trade {buy_trade['id']}: {profit:.2f} SOL")
        total_profit += profit
    
    print(f"\n💰 Total Profit: {total_profit:.2f} SOL")

if __name__ == "__main__":
    asyncio.run(main()) 