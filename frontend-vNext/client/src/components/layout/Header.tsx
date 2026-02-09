import { useState, useRef, useEffect } from "react";
import { Search, ChevronDown, LogOut, User, Settings } from "lucide-react";

export function Header({ title }: { title: string }) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const userInitials = "AD";
  const userName = "Angshuman Deb";
  const userEmail = "angshuman.deb@saama.com";

  return (
    <header className="h-[52px] bg-white border-b border-gray-200 shadow-sm sticky top-0 z-50 px-6 py-3 flex items-center justify-between gap-8">
      {/* LEFT SECTION - Logo & Branding */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <img 
          src="/saama-logo.svg" 
          alt="Saama" 
          className="h-8 flex-shrink-0"
          data-testid="img-logo"
        />
        <div className="w-px h-8 bg-gray-300 flex-shrink-0" />
        <span className="text-xl font-light text-gray-600 leading-none" data-testid="text-platform-name">
          Digital Study Platform
        </span>
      </div>

      {/* CENTER SECTION - Search Bar */}
      <div className="hidden lg:flex flex-1 max-w-2xl mx-8">
        <div className="relative w-full">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search sites, protocols, or investigators..."
            className="w-full py-2.5 pl-10 pr-4 border border-gray-300 rounded-full text-sm bg-white text-gray-900 placeholder:text-gray-500 focus:ring-2 focus:ring-gray-400 focus:border-transparent outline-none transition-all"
            data-testid="input-search"
          />
        </div>
      </div>

      {/* RIGHT SECTION - User Menu */}
      <div className="relative flex-shrink-0" ref={dropdownRef}>
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="flex items-center gap-2 px-3 py-2 rounded-full hover:bg-gray-100 transition-colors"
          data-testid="button-user-menu"
        >
          <div className="w-8 h-8 bg-black rounded-full flex items-center justify-center flex-shrink-0">
            <span className="text-xs font-semibold text-white" data-testid="text-user-initials">
              {userInitials}
            </span>
          </div>
          <span className="text-sm font-medium text-gray-900 hidden sm:inline" data-testid="text-user-name">
            {userName}
          </span>
          <ChevronDown className="w-4 h-4 text-gray-600 flex-shrink-0" />
        </button>

        {/* Dropdown Menu */}
        {dropdownOpen && (
          <div className="absolute right-0 mt-2 w-64 bg-white border border-gray-200 rounded-lg shadow-xl py-2 z-20">
            <div className="px-4 py-3 border-b border-gray-200">
              <p className="text-sm font-medium text-gray-900" data-testid="text-dropdown-name">{userName}</p>
              <p className="text-xs text-gray-500" data-testid="text-dropdown-email">{userEmail}</p>
            </div>
            <div className="py-1">
              <button 
                className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3"
                data-testid="button-profile"
              >
                <User className="w-4 h-4" />
                Profile
              </button>
              <button 
                className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-3"
                data-testid="button-settings"
              >
                <Settings className="w-4 h-4" />
                Settings
              </button>
            </div>
            <div className="border-t border-gray-200 pt-1">
              <button 
                className="w-full px-4 py-2 text-left text-sm text-gray-600 hover:bg-gray-100 flex items-center gap-3"
                data-testid="button-signout"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
