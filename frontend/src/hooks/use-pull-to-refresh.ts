import { useState, useRef } from 'react';

interface UsePullToRefreshOptions {
  onRefresh: () => void | Promise<void>;
  threshold?: number;
  maxPull?: number;
}

export function usePullToRefresh({ 
  onRefresh, 
  threshold = 80, 
  maxPull = 140 
}: UsePullToRefreshOptions) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const touchStartY = useRef(0);
  const isPulling = useRef(false);

  const onTouchStart = (e: React.TouchEvent<HTMLElement>) => {
    const scrollTop = e.currentTarget.scrollTop;
    if (scrollTop <= 1) { // Allow for minor subpixel differences
      touchStartY.current = e.touches[0].clientY;
      isPulling.current = true;
    } else {
      isPulling.current = false;
    }
  };

  const onTouchMove = (e: React.TouchEvent<HTMLElement>) => {
    if (!isPulling.current) return;

    const currentY = e.touches[0].clientY;
    const dy = currentY - touchStartY.current;

    if (e.currentTarget.scrollTop <= 0 && dy > 0) {
       // Damping effect
       const pull = Math.min(dy * 0.4, maxPull);
       setPullDistance(pull);
    } else {
        // If we scrolled down while pulling, stop the pull effect
       setPullDistance(0);
    }
  };

  const onTouchEnd = async () => {
    if (!isPulling.current) return;
    
    if (pullDistance >= threshold) {
      setIsRefreshing(true);
      setPullDistance(threshold); // Snap to threshold
      
      try {
        await Promise.resolve(onRefresh());
      } finally {
        setIsRefreshing(false);
        setPullDistance(0);
      }
    } else {
      setPullDistance(0); // Snap back
    }
    
    isPulling.current = false;
    touchStartY.current = 0;
  };

  return {
    isRefreshing,
    pullDistance,
    onTouchStart,
    onTouchMove,
    onTouchEnd
  };
}
