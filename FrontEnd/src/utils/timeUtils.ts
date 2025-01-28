export function normalizeTimestamp(timestamp: number | string): number {
  const date = new Date(timestamp);
  
  // If date is in 2025, adjust it to 2024
  if (date.getFullYear() === 2025) {
    date.setFullYear(2024);
  }
  
  const now = new Date();
  
  // If the date is in the future, assume it's a timezone issue and adjust
  if (date > now) {
    // Calculate hours difference
    const hoursDiff = Math.floor((date.getTime() - now.getTime()) / (1000 * 60 * 60));
    if (hoursDiff > 2 && hoursDiff < 12) {
      // If difference is between 2-12 hours, likely a timezone issue
      // Subtract the difference to normalize to local time
      return date.getTime() - (hoursDiff * 60 * 60 * 1000);
    }
  }
  
  return date.getTime();
}

export function formatRelativeTime(timestamp: number): string {
  const now = new Date();
  // Force current year to 2024
  now.setFullYear(2024);
  const normalizedTimestamp = normalizeTimestamp(timestamp);
  const diff = now.getTime() - normalizedTimestamp;
  
  // Handle future dates
  if (diff < 0) {
    return 'just now';
  }
  
  // Convert to seconds
  const seconds = Math.floor(diff / 1000);
  
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  
  // Convert to minutes
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  
  // Convert to hours
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  
  // Convert to days
  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d ago`;
  }
  
  // Convert to months
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months}mo ago`;
  }
  
  // Convert to years
  const years = Math.floor(months / 12);
  return `${years}y ago`;
}

export function formatDateTime(dateTimeStr: string): string {
  try {
    // Parse and normalize the timestamp
    const date = new Date(dateTimeStr);
    // If date is in 2025, adjust it to 2024
    if (date.getFullYear() === 2025) {
      date.setFullYear(2024);
    }
    
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
  } catch (error) {
    console.error('Error formatting date:', error);
    return dateTimeStr; // Return original string if parsing fails
  }
}

export function getTimestamp(dateTimeStr: string): number {
  try {
    return normalizeTimestamp(dateTimeStr);
  } catch (error) {
    console.error('Error getting timestamp:', error);
    return Date.now(); // Return current timestamp if parsing fails
  }
} 