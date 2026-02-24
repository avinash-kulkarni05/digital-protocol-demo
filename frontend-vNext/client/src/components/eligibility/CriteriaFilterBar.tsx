import * as React from "react";
import { useState, useMemo, useCallback, useEffect } from "react";
import {
  Search,
  Filter,
  X,
  ChevronDown,
  Zap,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { QueryableBlock, AtomicCriterion } from "@/lib/qebValidation";

export interface FilterState {
  searchQuery: string;
  type: "all" | "inclusion" | "exclusion";
  status: "all" | "fully_queryable" | "partially_queryable" | "requires_manual";
  category: string;
  showKillerOnly: boolean;
  showUnmappedOnly: boolean;
  showComplexOnly: boolean;
}

export const DEFAULT_FILTER_STATE: FilterState = {
  searchQuery: "",
  type: "all",
  status: "all",
  category: "all",
  showKillerOnly: false,
  showUnmappedOnly: false,
  showComplexOnly: false,
};

interface CriteriaFilterBarProps {
  queryableBlocks: QueryableBlock[];
  atomicCriteria: AtomicCriterion[];
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  filteredCount: number;
  totalCount: number;
}

export function CriteriaFilterBar({
  queryableBlocks,
  atomicCriteria,
  filters,
  onFiltersChange,
  filteredCount,
  totalCount,
}: CriteriaFilterBarProps) {
  const [searchInput, setSearchInput] = useState(filters.searchQuery);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filters.searchQuery) {
        onFiltersChange({ ...filters, searchQuery: searchInput });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Extract unique categories from data
  const categories = useMemo(() => {
    const cats = new Set<string>();
    queryableBlocks.forEach(qeb => {
      if (qeb.clinicalCategory) cats.add(qeb.clinicalCategory);
    });
    return Array.from(cats).sort();
  }, [queryableBlocks]);

  // Count active filters
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.searchQuery) count++;
    if (filters.type !== "all") count++;
    if (filters.status !== "all") count++;
    if (filters.category !== "all") count++;
    if (filters.showKillerOnly) count++;
    if (filters.showUnmappedOnly) count++;
    if (filters.showComplexOnly) count++;
    return count;
  }, [filters]);

  const clearAllFilters = () => {
    setSearchInput("");
    onFiltersChange(DEFAULT_FILTER_STATE);
  };

  const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    onFiltersChange({ ...filters, [key]: value });
  };

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + K to focus search
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        const searchInput = document.getElementById("criteria-search");
        searchInput?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="space-y-3">
      {/* Search Row */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            id="criteria-search"
            type="text"
            placeholder="Search criteria text, concepts, categories... (Cmd+K)"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9 pr-8 h-9 text-sm"
          />
          {searchInput && (
            <button
              onClick={() => {
                setSearchInput("");
                updateFilter("searchQuery", "");
              }}
              className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Filter Popover */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-9 gap-2">
              <Filter className="w-4 h-4" />
              Filters
              {activeFilterCount > 0 && (
                <Badge className="ml-1 h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px] bg-gray-700">
                  {activeFilterCount}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-4" align="end">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-medium text-sm">Filter Criteria</h4>
                {activeFilterCount > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearAllFilters}
                    className="h-7 text-xs text-gray-600 hover:text-gray-800"
                  >
                    Clear all
                  </Button>
                )}
              </div>

              {/* Type Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-700">Criterion Type</label>
                <Select value={filters.type} onValueChange={(v) => updateFilter("type", v as FilterState["type"])}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="inclusion">Inclusion Only</SelectItem>
                    <SelectItem value="exclusion">Exclusion Only</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Status Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-700">Queryable Status</label>
                <Select value={filters.status} onValueChange={(v) => updateFilter("status", v as FilterState["status"])}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="fully_queryable">
                      <span className="flex items-center gap-2">
                        <CheckCircle2 className="w-3 h-3 text-gray-700" />
                        Fully Queryable
                      </span>
                    </SelectItem>
                    <SelectItem value="partially_queryable">
                      <span className="flex items-center gap-2">
                        <AlertCircle className="w-3 h-3 text-gray-500" />
                        Needs Mapping
                      </span>
                    </SelectItem>
                    <SelectItem value="requires_manual">
                      <span className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-gray-400" />
                        Manual Review
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Category Filter */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-700">Clinical Category</label>
                <Select value={filters.category} onValueChange={(v) => updateFilter("category", v)}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    {categories.map(cat => (
                      <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Separator */}
              <div className="border-t border-gray-100 pt-3">
                <label className="text-xs font-medium text-gray-700 mb-2 block">Quick Filters</label>
                <div className="space-y-2">
                  {/* Killer Criteria Toggle */}
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.showKillerOnly}
                      onChange={(e) => updateFilter("showKillerOnly", e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-gray-600 focus:ring-gray-500"
                    />
                    <span className="text-sm text-gray-700 flex items-center gap-1">
                      <Zap className="w-3.5 h-3.5 text-gray-500" />
                      High Impact Only
                    </span>
                  </label>

                  {/* Unmapped Toggle */}
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.showUnmappedOnly}
                      onChange={(e) => updateFilter("showUnmappedOnly", e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-gray-600 focus:ring-gray-500"
                    />
                    <span className="text-sm text-gray-700 flex items-center gap-1">
                      <AlertCircle className="w-3.5 h-3.5 text-gray-500" />
                      Unmapped Concepts
                    </span>
                  </label>

                  {/* Complex Logic Toggle */}
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.showComplexOnly}
                      onChange={(e) => updateFilter("showComplexOnly", e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-gray-600 focus:ring-gray-500"
                    />
                    <span className="text-sm text-gray-700">
                      Complex Logic Only
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Active Filters Row */}
      {activeFilterCount > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500">
            Showing {filteredCount} of {totalCount} criteria
          </span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {filters.searchQuery && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Search: "{filters.searchQuery.slice(0, 20)}{filters.searchQuery.length > 20 ? '...' : ''}"
                <button
                  onClick={() => {
                    setSearchInput("");
                    updateFilter("searchQuery", "");
                  }}
                  className="ml-1 hover:bg-gray-300 rounded-full p-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.type !== "all" && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1 capitalize">
                {filters.type}
                <button onClick={() => updateFilter("type", "all")} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.status !== "all" && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                {filters.status.replace(/_/g, " ")}
                <button onClick={() => updateFilter("status", "all")} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.category !== "all" && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                {filters.category}
                <button onClick={() => updateFilter("category", "all")} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.showKillerOnly && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                <Zap className="w-3 h-3" /> High Impact
                <button onClick={() => updateFilter("showKillerOnly", false)} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.showUnmappedOnly && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Unmapped
                <button onClick={() => updateFilter("showUnmappedOnly", false)} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            {filters.showComplexOnly && (
              <Badge variant="secondary" className="text-xs gap-1 pr-1">
                Complex Logic
                <button onClick={() => updateFilter("showComplexOnly", false)} className="ml-1 hover:bg-gray-300 rounded-full p-0.5">
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Helper function to filter criteria based on filter state
export function filterCriteria(
  queryableBlocks: QueryableBlock[],
  atomicCriteria: AtomicCriterion[],
  filters: FilterState,
  atomicLookup: Map<string, AtomicCriterion>
): QueryableBlock[] {
  return queryableBlocks.filter(qeb => {
    // Type filter
    if (filters.type !== "all" && qeb.criterionType !== filters.type) {
      return false;
    }

    // Status filter
    if (filters.status !== "all" && qeb.queryableStatus !== filters.status) {
      return false;
    }

    // Category filter
    if (filters.category !== "all" && qeb.clinicalCategory !== filters.category) {
      return false;
    }

    // Killer criteria filter
    if (filters.showKillerOnly && !qeb.isKillerCriterion) {
      return false;
    }

    // Complex logic filter
    if (filters.showComplexOnly && qeb.internalLogic !== "COMPLEX") {
      return false;
    }

    // Unmapped filter - check if any atomics have unmapped concepts
    if (filters.showUnmappedOnly) {
      const hasUnmapped = qeb.atomicIds.some(atomicId => {
        const atomic = atomicLookup.get(atomicId);
        if (!atomic?.omopQuery) return true;
        return atomic.omopQuery.conceptIds.some(id => id === null || id === 0);
      });
      if (!hasUnmapped) return false;
    }

    // Search query filter
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      const searchFields = [
        qeb.protocolText,
        qeb.clinicalCategory,
        qeb.clinicalName,
        qeb.clinicalDescription,
        qeb.originalCriterionId,
        ...qeb.omopConcepts.map(c => c.conceptName),
        ...qeb.omopConcepts.map(c => c.domain),
      ].filter(Boolean).join(" ").toLowerCase();

      if (!searchFields.includes(query)) {
        return false;
      }
    }

    return true;
  });
}
