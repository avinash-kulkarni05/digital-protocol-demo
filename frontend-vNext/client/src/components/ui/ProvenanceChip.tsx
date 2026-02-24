import { FileText } from "lucide-react";

interface ProvenanceChipProps {
  provenance: any;
  onViewSource?: (page: number) => void;
  className?: string;
}

/**
 * Extracts page number from various provenance formats:
 * - { explicit: { page_number: N } }
 * - { page_number: N }
 * - N (direct number)
 */
export function getPageNumber(provenance: any): number | null {
  if (!provenance) return null;
  if (typeof provenance === 'number') return provenance;
  return provenance.explicit?.page_number || provenance.page_number || null;
}

/**
 * Shared ProvenanceChip component for consistent display across all views.
 * Shows a "p. XX" button that links to the PDF source.
 */
export function ProvenanceChip({ provenance, onViewSource, className = "" }: ProvenanceChipProps) {
  const pageNumber = getPageNumber(provenance);
  if (!pageNumber || !onViewSource) return null;

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onViewSource(pageNumber);
      }}
      className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors ${className}`}
      data-testid={`provenance-link-page-${pageNumber}`}
    >
      <FileText className="w-3 h-3" />
      p. {pageNumber}
    </button>
  );
}

export default ProvenanceChip;
