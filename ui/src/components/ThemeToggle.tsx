// ui/src/components/ThemeToggle.tsx
import React, { useEffect, useState } from 'react';
import { SunIcon, MoonIcon } from '@heroicons/react/24/outline';

const ThemeToggle: React.FC = () => {
  // Initialise from localStorage (the same source that main.tsx uses)
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem('theme');
    // If nothing is stored we default to dark - exactly what main.tsx does
    return saved !== 'light';
  });

  const toggle = () => {
    const root = document.documentElement;
    const newIsDark = !isDark;
    
    if (newIsDark) {
      root.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
    
    setIsDark(newIsDark);
  };

  return (
    <button
      onClick={toggle}
      className="p-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700"
      aria-label="Toggle light/dark theme"
    >
      {isDark ? (
        <SunIcon className="w-5 h-5 text-yellow-400" />
      ) : (
        <MoonIcon className="w-5 h-5 text-gray-600" />
      )}
    </button>
  );
};

export default ThemeToggle;