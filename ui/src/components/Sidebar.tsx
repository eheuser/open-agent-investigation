// ui/src/components/Sidebar.tsx
import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { 
  PlusIcon, 
  ChatBubbleLeftIcon,
  TrashIcon,
  PencilIcon,
  ExclamationTriangleIcon,
  Cog6ToothIcon,
  Bars3Icon,
  XMarkIcon,
  BeakerIcon,
  ArrowRightOnRectangleIcon,
  UserIcon,
  QueueListIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline';
import { 
  getInvestigations, 
  createInvestigation, 
  updateInvestigation, 
  deleteInvestigation as deleteInvestigationAPI,
  Investigation 
} from '../services/investigations';
import { useAuth } from '../contexts/AuthContext';
import { useJobs } from '../contexts/JobsContext';
import ThemeToggle from './ThemeToggle';
 
const Sidebar: React.FC<{ isOpen: boolean; onToggle: () => void }> = ({ isOpen, onToggle }) => {
  const [list, setList] = useState<Investigation[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [investigationToDelete, setInvestigationToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorModalOpen, setErrorModalOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
        const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  
  // Get jobs context (may be undefined if not wrapped in JobsProvider)
  let activeJobsCount = 0;
  let hasRunningJobs = false;
  let setShowJobs: (show: boolean) => void = () => {};
  
  try {
    const jobsContext = useJobs();
    activeJobsCount = jobsContext.activeJobsCount;
    hasRunningJobs = jobsContext.hasRunningJobs;
    setShowJobs = jobsContext.setShowJobs;
  } catch (err) {
    // Jobs context not available (e.g., on non-investigation pages)
  }

  // Load investigations from API on mount and when location changes
  useEffect(() => {
    loadInvestigations();
  }, [location.pathname]);

  const loadInvestigations = async () => {
    setIsLoading(true);
    try {
      const investigations = await getInvestigations();
      setList(investigations);
    } catch (error) {
      console.error('Failed to load investigations:', error);
    } finally {
      setIsLoading(false);
    }
  };

        const create = async () => {
    setIsCreating(true);
    try {
      const newInv = await createInvestigation({ title: 'New Investigation' });
      setList(prev => [newInv, ...prev]);
      navigate(`/investigation/${newInv.investigation_id}`);
    } catch (error: any) {
      console.error('Failed to create investigation:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Unknown error';
      setErrorMessage(`Failed to create investigation: ${errMsg}`);
      setErrorModalOpen(true);
    } finally {
      setIsCreating(false);
    }
  };

      const handleDeleteClick = (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setInvestigationToDelete(id);
    setDeleteModalOpen(true);
  };

        const confirmDelete = async () => {
    if (!investigationToDelete) return;
    
    setIsDeleting(true);
    try {
      await deleteInvestigationAPI(investigationToDelete);
      const updatedList = list.filter(inv => inv.investigation_id !== investigationToDelete);
      setList(updatedList);
      setDeleteModalOpen(false);
      
      // Check if we're currently viewing the deleted investigation
      const currentPath = location.pathname;
      const isViewingDeletedInvestigation = currentPath.includes(`/investigation/${investigationToDelete}`);
      
      // Navigate to dashboard if:
      // 1. We deleted the investigation we're currently viewing, OR
      // 2. There are no investigations left
      if (isViewingDeletedInvestigation || updatedList.length === 0) {
        navigate('/');
      }
      
      setInvestigationToDelete(null);
    } catch (error) {
      console.error('Failed to delete investigation:', error);
      setDeleteModalOpen(false);
      setInvestigationToDelete(null);
      setErrorMessage('Failed to delete investigation. Please try again.');
      setErrorModalOpen(true);
    } finally {
      setIsDeleting(false);
    }
  };

  const cancelDelete = () => {
    setDeleteModalOpen(false);
    setInvestigationToDelete(null);
  };

  const startEdit = (inv: Investigation, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingId(inv.investigation_id);
    setEditTitle(inv.title);
  };

      const saveEdit = async (id: string) => {
    if (!editTitle.trim()) {
      cancelEdit();
      return;
    }
    
    try {
      await updateInvestigation(id, { title: editTitle });
      setList(prev => prev.map(inv => 
        inv.investigation_id === id ? { ...inv, title: editTitle } : inv
      ));
      setEditingId(null);
    } catch (error) {
      console.error('Failed to update investigation:', error);
      setErrorMessage('Failed to update investigation title. Please try again.');
      setErrorModalOpen(true);
    }
  };

    const cancelEdit = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
    setShowLogoutConfirm(false);
  };

    return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}
      
                                    {/* Sidebar */}
                  <aside className={`
        fixed lg:relative inset-y-0 left-0 z-50
        bg-gray-50 dark:bg-[#171717] h-full flex flex-col
        transition-all duration-200 ease-in-out
        ${isOpen ? 'w-64 translate-x-0' : 'w-12 translate-x-0'}
        ${!isOpen && 'items-center'}
      `}>
      {/* Header with Logo and Collapse Button */}
      <div className={`flex items-center ${isOpen ? 'justify-between' : 'justify-center'}`} style={{ height: '52px', paddingLeft: '12px', paddingRight: '12px' }}>
        {isOpen ? (
          <>
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <BeakerIcon className="w-5 h-5 flex-shrink-0 text-blue-600 dark:text-blue-400" />
              <span className="font-bold text-sm text-gray-900 dark:text-white whitespace-nowrap">Open Agent Investigation</span>
            </div>
            <button
              onClick={onToggle}
              className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors flex-shrink-0"
              title="Close sidebar"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600 dark:text-gray-400">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="9" y1="3" x2="9" y2="21"></line>
              </svg>
            </button>
          </>
                ) : (
          <button
            onClick={onToggle}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
            title="Open sidebar"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600 dark:text-gray-400">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="9" y1="3" x2="9" y2="21"></line>
            </svg>
          </button>
        )}
      </div>

            {/* New Investigation Button */}
      {isOpen && (
        <div className="px-2 pb-1">
                                <button
          onClick={create}
          disabled={isCreating}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <PlusIcon className="w-5 h-5" />
                    <span className="text-sm font-medium">
            {isCreating ? 'Creating...' : 'New Investigation'}
          </span>
        </button>
        </div>
      )}

                        {/* Investigation List */}
      {isOpen && (
        <nav className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5 scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600 scrollbar-track-transparent hover:scrollbar-thumb-gray-400 dark:hover:scrollbar-thumb-gray-500">
        {isLoading ? (
          <div className="text-center py-8 px-4 text-gray-500 dark:text-gray-400 text-sm">
            Loading investigations...
          </div>
        ) : list.length === 0 ? (
          <div className="text-center py-8 px-4 text-gray-500 dark:text-gray-400 text-sm">
            No investigations yet
          </div>
        ) : (
          list.map(inv => (
            <div key={inv.investigation_id} className="group relative">
              {editingId === inv.investigation_id ? (
                <div className="flex items-center gap-1 px-3 py-2">
                  <input
                    type="text"
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') saveEdit(inv.investigation_id);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                    className="flex-1 bg-transparent border-b border-blue-500 dark:border-gray-400 text-sm focus:outline-none text-gray-900 dark:text-gray-100"
                    autoFocus
                  />
                  <button
                    onClick={() => saveEdit(inv.investigation_id)}
                    className="text-xs text-blue-600 dark:text-gray-400 hover:underline"
                  >
                    Save
                  </button>
                </div>
              ) : (
                <NavLink
                  to={`/investigation/${inv.investigation_id}`}
                                                      className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors relative text-sm ${
                      isActive 
                        ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-white' 
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`
                  }
                >
                  <ChatBubbleLeftIcon className="w-4 h-4 flex-shrink-0" />
                  <span className="flex-1 text-sm truncate">
                    {inv.title || 'Untitled'}
                  </span>
                  <div className="hidden group-hover:flex items-center gap-1">
                    <button
                      onClick={(e) => startEdit(inv, e)}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                      title="Rename"
                    >
                      <PencilIcon className="w-3.5 h-3.5" />
                    </button>
                                                            <button
                      onClick={(e) => handleDeleteClick(inv.investigation_id, e)}
                      className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded text-red-600 dark:text-red-400"
                      title="Delete"
                    >
                      <TrashIcon className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </NavLink>
              )}
            </div>
          ))
                                                                )}
        </nav>
      )}

                                                                                                                                                {/* User Menu Section */}
      {isOpen && (
        <div className="p-2 border-t border-gray-200 dark:border-gray-700 relative space-y-1">
                                                                                {/* Jobs Button */}
          <button
            onClick={() => setShowJobs(true)}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
            title="View Job Queue"
          >
            {activeJobsCount === 0 && (
              <svg 
                className="w-5 h-5 flex-shrink-0 text-gray-400 dark:text-gray-500" 
                viewBox="0 0 24 24" 
                fill="none"
              >
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
              </svg>
            )}
            <span className="text-sm flex-1 text-left">Jobs</span>
            {activeJobsCount > 0 && (
              <span className="inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold leading-none text-white bg-blue-500 rounded-full animate-pulse">
                {activeJobsCount}
              </span>
            )}
          </button>

          {/* User Menu Button */}
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
              <span className="text-white text-xs font-semibold">
                {user?.username?.charAt(0).toUpperCase() || 'U'}
              </span>
            </div>
            <span className="text-sm truncate flex-1 text-left font-medium">{user?.username}</span>
                    </button>

                    {/* User Dropdown Menu */}
          {userMenuOpen && (
            <div className="absolute bottom-full left-2 right-2 mb-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1">
              <NavLink
                to="/playbooks"
                onClick={() => setUserMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 transition-colors text-sm ${
                    isActive 
                      ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' 
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`
                }
              >
                <BookOpenIcon className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">Playbooks</span>
              </NavLink>
              
              <NavLink
                to="/settings"
                onClick={() => setUserMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 transition-colors text-sm ${
                    isActive 
                      ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' 
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`
                }
              >
                <Cog6ToothIcon className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">Settings</span>
              </NavLink>
              
              <div className="px-3 py-2.5 flex items-center gap-3 text-sm text-gray-700 dark:text-gray-300">
                <div className="flex-shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                </div>
                <span className="text-sm flex-1">Theme</span>
                <ThemeToggle />
              </div>

              <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
              
              <button
                onClick={() => {
                  setUserMenuOpen(false);
                  setShowLogoutConfirm(true);
                }}
                className="w-full flex items-center gap-3 px-3 py-2.5 transition-colors text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <ArrowRightOnRectangleIcon className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm">Logout</span>
              </button>
            </div>
          )}
                </div>
      )}

                                                                                    {/* Collapsed Jobs Icon */}
      {!isOpen && (
        <div className="p-2">
          <button
            onClick={() => setShowJobs(true)}
            className="w-full p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors group relative flex items-center justify-center"
            title="View Job Queue"
          >
            {activeJobsCount === 0 ? (
              <svg 
                className="w-5 h-5 text-gray-400 dark:text-gray-500" 
                viewBox="0 0 24 24" 
                fill="none"
              >
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
              </svg>
            ) : (
              <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-bold text-white bg-blue-500 rounded-full animate-pulse">
                {activeJobsCount}
              </span>
            )}
          </button>
        </div>
      )}

          </aside>

            {/* Delete Confirmation Modal */}
      {deleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop - prevent clicks when deleting */}
          <div 
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={isDeleting ? undefined : cancelDelete}
          />
          
          {/* Modal */}
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            {/* Loading Overlay */}
            {isDeleting && (
              <div className="absolute inset-0 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-lg flex items-center justify-center z-10">
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 border-4 border-red-200 dark:border-red-900/30 border-t-red-600 dark:border-t-red-400 rounded-full animate-spin"></div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">Deleting investigation...</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400">This may take a moment</p>
                </div>
              </div>
            )}
            
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Delete Investigation
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to delete this investigation? This action cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={cancelDelete}
                    disabled={isDeleting}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={confirmDelete}
                    disabled={isDeleting}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isDeleting ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error Modal */}
      {errorModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div 
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setErrorModalOpen(false)}
          />
          
          {/* Modal */}
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-600 dark:text-red-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Error
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  {errorMessage}
                </p>
                <div className="flex justify-end">
                  <button
                    onClick={() => setErrorModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-gray-700 dark:hover:bg-gray-600 transition-colors"
                  >
                    OK
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
                                                )}

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div 
            className="absolute inset-0 bg-black bg-opacity-50"
            onClick={() => setShowLogoutConfirm(false)}
          />
          <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                  <ArrowRightOnRectangleIcon className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Confirm Logout
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  Are you sure you want to logout?
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setShowLogoutConfirm(false)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleLogout}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Logout
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}      
    </>
  );
};

export default Sidebar;