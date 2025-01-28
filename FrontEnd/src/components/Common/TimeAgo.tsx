import { formatDistanceToNow } from 'date-fns';
import { useEffect, useState } from 'react';

export default function TimeAgo({ date }: { date: string }) {
  const [timeAgo, setTimeAgo] = useState('');

  useEffect(() => {
    const updateTime = () => {
      try {
        // Clean date string by removing trailing non-digit characters
        const cleanedDate = date.replace(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\D.*$/, '$1');
        const parsedDate = new Date(cleanedDate);
        setTimeAgo(formatDistanceToNow(parsedDate, { addSuffix: true }));
      } catch (e) {
        setTimeAgo('Invalid date');
      }
    };

    // Update immediately and set interval
    updateTime();
    const interval = setInterval(updateTime, 1000);

    return () => clearInterval(interval);
  }, [date]);

  return <span>{timeAgo}</span>;
} 