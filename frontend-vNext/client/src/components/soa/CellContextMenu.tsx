import { ReactNode } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuLabel,
} from "@/components/ui/context-menu";
import {
  Copy,
  Eraser,
  Merge,
  Split,
  Eye,
  Trash2,
  FileText,
} from "lucide-react";

interface CellContextMenuProps {
  children: ReactNode;
  cellValue?: string;
  hasSelection?: boolean;
  selectionCount?: number;
  canMerge?: boolean;
  canSplit?: boolean;
  hasFootnotes?: boolean;
  pageNumber?: number;
  onCopy?: () => void;
  onClear?: () => void;
  onMerge?: () => void;
  onSplit?: () => void;
  onViewSource?: () => void;
  onViewFootnotes?: () => void;
  onDelete?: () => void;
}

export function CellContextMenu({
  children,
  cellValue,
  hasSelection = false,
  selectionCount = 1,
  canMerge = false,
  canSplit = false,
  hasFootnotes = false,
  pageNumber,
  onCopy,
  onClear,
  onMerge,
  onSplit,
  onViewSource,
  onViewFootnotes,
  onDelete,
}: CellContextMenuProps) {
  return (
    <ContextMenu>
      {children}
      <ContextMenuContent className="w-56">
        {/* Selection Info */}
        {hasSelection && selectionCount > 1 && (
          <>
            <ContextMenuLabel className="text-xs text-muted-foreground">
              {selectionCount} cells selected
            </ContextMenuLabel>
            <ContextMenuSeparator />
          </>
        )}

        {/* Copy */}
        {onCopy && (
          <ContextMenuItem onClick={onCopy} className="gap-2">
            <Copy className="w-4 h-4" />
            Copy Value
            <ContextMenuShortcut>Ctrl+C</ContextMenuShortcut>
          </ContextMenuItem>
        )}

        {/* Clear Cell */}
        {onClear && (
          <ContextMenuItem onClick={onClear} className="gap-2">
            <Eraser className="w-4 h-4" />
            Clear Cell{selectionCount > 1 ? 's' : ''}
          </ContextMenuItem>
        )}

        {/* Merge/Split Operations */}
        {(canMerge || canSplit) && (
          <>
            <ContextMenuSeparator />

            {canMerge && onMerge && (
              <ContextMenuItem onClick={onMerge} className="gap-2">
                <Merge className="w-4 h-4" />
                Merge Cells
                <ContextMenuShortcut>Ctrl+M</ContextMenuShortcut>
              </ContextMenuItem>
            )}

            {canSplit && onSplit && (
              <ContextMenuItem onClick={onSplit} className="gap-2">
                <Split className="w-4 h-4" />
                Split Cell
              </ContextMenuItem>
            )}
          </>
        )}

        {/* View Operations */}
        {(onViewSource || onViewFootnotes) && (
          <>
            <ContextMenuSeparator />

            {onViewSource && pageNumber && (
              <ContextMenuItem onClick={onViewSource} className="gap-2">
                <Eye className="w-4 h-4" />
                View in PDF (Page {pageNumber})
              </ContextMenuItem>
            )}

            {onViewFootnotes && hasFootnotes && (
              <ContextMenuItem onClick={onViewFootnotes} className="gap-2">
                <FileText className="w-4 h-4" />
                View Footnotes
              </ContextMenuItem>
            )}
          </>
        )}

        {/* Destructive Actions */}
        {onDelete && (
          <>
            <ContextMenuSeparator />
            <ContextMenuItem
              onClick={onDelete}
              className="gap-2 text-red-600 focus:text-red-600 focus:bg-red-50"
            >
              <Trash2 className="w-4 h-4" />
              Delete Cell{selectionCount > 1 ? 's' : ''}
            </ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  );
}

// Simplified version for basic cell interactions
interface SimpleCellContextMenuProps {
  children: ReactNode;
  onCopy?: () => void;
  onViewSource?: () => void;
  pageNumber?: number;
}

export function SimpleCellContextMenu({
  children,
  onCopy,
  onViewSource,
  pageNumber,
}: SimpleCellContextMenuProps) {
  return (
    <ContextMenu>
      {children}
      <ContextMenuContent className="w-48">
        {onCopy && (
          <ContextMenuItem onClick={onCopy} className="gap-2">
            <Copy className="w-4 h-4" />
            Copy Value
            <ContextMenuShortcut>Ctrl+C</ContextMenuShortcut>
          </ContextMenuItem>
        )}

        {onViewSource && pageNumber && (
          <ContextMenuItem onClick={onViewSource} className="gap-2">
            <Eye className="w-4 h-4" />
            View in PDF
          </ContextMenuItem>
        )}
      </ContextMenuContent>
    </ContextMenu>
  );
}

// Context menu for table headers (row/column operations)
interface HeaderContextMenuProps {
  children: ReactNode;
  type: 'row' | 'column';
  onInsertBefore?: () => void;
  onInsertAfter?: () => void;
  onDelete?: () => void;
  onCopy?: () => void;
}

export function HeaderContextMenu({
  children,
  type,
  onInsertBefore,
  onInsertAfter,
  onDelete,
  onCopy,
}: HeaderContextMenuProps) {
  const typeLabel = type === 'row' ? 'Row' : 'Column';

  return (
    <ContextMenu>
      {children}
      <ContextMenuContent className="w-48">
        <ContextMenuLabel className="text-xs text-muted-foreground">
          {typeLabel} Actions
        </ContextMenuLabel>
        <ContextMenuSeparator />

        {onCopy && (
          <ContextMenuItem onClick={onCopy} className="gap-2">
            <Copy className="w-4 h-4" />
            Copy {typeLabel}
          </ContextMenuItem>
        )}

        {onInsertBefore && (
          <ContextMenuItem onClick={onInsertBefore} className="gap-2">
            Insert {typeLabel} Before
          </ContextMenuItem>
        )}

        {onInsertAfter && (
          <ContextMenuItem onClick={onInsertAfter} className="gap-2">
            Insert {typeLabel} After
          </ContextMenuItem>
        )}

        {onDelete && (
          <>
            <ContextMenuSeparator />
            <ContextMenuItem
              onClick={onDelete}
              className="gap-2 text-red-600 focus:text-red-600 focus:bg-red-50"
            >
              <Trash2 className="w-4 h-4" />
              Delete {typeLabel}
            </ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
  );
}
