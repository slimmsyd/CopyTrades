export interface TrackedTrade {
  id: string;
  date_time: string;
  token_address: string;
  buy_price: number;
  buy_price_usd?: number;
  close_price: number | null;
  current_price: number;
  current_price_usd?: number;
  profit: number;
  profit_percentage: number;
  status: string;
  result: string;
  transaction_link: string;
  amount_in_sol: number;
  amount_in_usd?: number;
  token_amount: number;
  wallet_group: string | null;
  trade_type: 'buy' | 'sell';
  closed_reason?: 'manual' | 'stop_loss' | 'take_profit' | 'sold';
  closed_at?: string;
  partial_sales?: Array<{
    amount: number;
    price: number;
    date_time: string;
  }>;
}

export interface TrackedTradesData {
  [key: string]: TrackedTrade;
}

export interface WalletGroup {
  id: string;
  name: string;
  address: string;
  trades: TrackedTrade[];
  totalProfit: number;
  winRate: number;
  successfulTrades: number;
  totalTrades: number;
}