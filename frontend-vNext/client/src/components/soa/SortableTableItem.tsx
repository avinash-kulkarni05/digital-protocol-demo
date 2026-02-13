import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { cn } from '@/lib/utils';
import { GripVertical, FileText } from 'lucide-react';

interface SortableTableItemProps {
  tableId: string;
  pageRange?: { start: number; end: number };
  category?: string;
  isDragging?: boolean;
  isOverlay?: boolean;
  onPageClick?: (page: number) => void;
}

export function SortableTableItem({
  tableId,
  pageRange,
  category,
  isDragging = false,
  isOverlay = false,
  onPageClick,
}: SortableTableItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging: isSortableDragging,
  } = useSortable({ id: tableId });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const isCurrentlyDragging = isDragging || isSortableDragging;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-lg border transition-all",
        "bg-white hover:bg-gray-50",
        isCurrentlyDragging && "opacity-50 shadow-lg ring-2 ring-primary",
        isOverlay && "shadow-xl bg-white opacity-100",
        !isCurrentlyDragging && "border-gray-200"
      )}
    >
      {/* Drag Handle */}
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing p-1 rounded hover:bg-gray-100"
      >
        <GripVertical className="w-4 h-4 text-gray-400" />
      </div>

      {/* Table Icon */}
      <FileText className="w-4 h-4 text-gray-500 flex-shrink-0" />

      {/* Table Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-medium text-gray-800">
            {tableId}
          </span>
          {category && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 uppercase">
              {category}
            </span>
          )}
        </div>
        {pageRange && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onPageClick?.(pageRange.start);
            }}
            className="text-xs text-blue-600 hover:text-blue-800 hover:underline cursor-pointer text-left"
          >
            pp. {pageRange.start}-{pageRange.end}
          </button>
        )}
      </div>
    </div>
  );
}

// Static version for drag overlay (doesn't need sortable context)
export function TableItemOverlay({
  tableId,
  pageRange,
  category,
}: Omit<SortableTableItemProps, 'isDragging' | 'isOverlay'>) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-2 rounded-lg border",
        "bg-white shadow-xl ring-2 ring-primary border-primary"
      )}
    >
      {/* Drag Handle */}
      <div className="p-1 rounded">
        <GripVertical className="w-4 h-4 text-primary" />
      </div>

      {/* Table Icon */}
      <FileText className="w-4 h-4 text-primary flex-shrink-0" />

      {/* Table Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-medium text-gray-800">
            {tableId}
          </span>
          {category && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary uppercase">
              {category}
            </span>
          )}
        </div>
        {pageRange && (
          <span className="text-xs text-gray-500">
            pp. {pageRange.start}-{pageRange.end}
          </span>
        )}
      </div>
    </div>
  );
}
