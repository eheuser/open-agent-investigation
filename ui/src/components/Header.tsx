import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import ThemeToggle from './ThemeToggle';
import { XMarkIcon } from '@heroicons/react/24/outline';

const Header: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
    setShowLogoutConfirm(false);
  };

    return (
    <header className="bg-white dark:bg-gray-900 px-4 py-3">
      <div className="flex items-center justify-between">
        {/* Left side - Toggle and Title */}
                                <div className="flex items-center gap-3">
          <h1 className="text-sm font-medium text-gray-900 dark:text-white hidden sm:block">
            Open Agent Investigation
          </h1>
        </div>

        {/* Right side - Theme toggle and user actions */}
        <div className="flex items-center gap-3">
          <ThemeToggle />
          
          {user && (
            <>
              <div className="hidden sm:block text-sm text-gray-700 dark:text-gray-300">
                {user.username}
              </div>
                                          <button
                onClick={() => setShowLogoutConfirm(true)}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              >
                Logout
              </button>
            </>
          )}
                </div>
      </div>

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-md w-full">
            <div className="flex items-center justify-between p-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Confirm Logout
              </h3>
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <XMarkIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              </button>
            </div>
            
            <div className="p-6">
              <p className="text-gray-700 dark:text-gray-300 mb-6">
                Are you sure you want to logout?
              </p>
              
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowLogoutConfirm(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
                >
                  Logout
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

export default Header;