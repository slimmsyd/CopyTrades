export interface TokenInfo {
  address: string;
  symbol: string;
  name: string;
  decimals: number;
  logoURI?: string;
  price?: number;
}

export interface Trade {
  signature: string;
  type: 'buy' | 'sell';
  token_address: string;
  value: string;
  timestamp: number;
  html: string;
  profit?: number;
  amount?: number;
  entryPrice?: number;
  currentPrice?: number;
  status: string;
  profit_percentage: number;
  date_time: string;
  transaction_link: string;
  token_amount: number;
  buy_price: number;
  trade_type: 'buy' | 'sell';
  id: string;
  initial_token_amount?: number;
}

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
  initial_token_amount?: number;
}

export interface SavedWallet {
  address: string;
  name: string;
  timestamp: number;
}

export interface TradeWithStats {
  tokenAddress: string;
  entryPrice: number;
  currentPrice: number;
  volume24h?: number;
  marketCap?: number;
  signature: string;
  timestamp: number;
  lastUpdate: number;
  priceError?: string;
}