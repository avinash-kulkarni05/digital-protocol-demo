import { useState, useMemo } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
} from '@dnd-kit/core';
import {
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Plus, Check, X, Layers, Info, AlertTriangle, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, FileText } from 'lucide-react';
import { MergeGroupCard } from './MergeGroupCard';
import { TableItemOverlay } from './SortableTableItem';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { Document, Page, pdfjs } from 'react-pdf';
import type { MergePlan, MergeGroup, MergePlanConfirmation as MergePlanConfirmationType, ConfirmedGroup } from '@/lib/api';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  `pdfjs-dist/build/pdf.worker.min.mjs`,
  import.meta.url
).toString();

interface EditableGroup extends MergeGroup {
  isModified: boolean;
}

interface MergePlanConfirmationProps {
  mergePlan: MergePlan;
  pdfUrl?: string;
  onConfirm: (confirmation: MergePlanConfirmationType) => void;
  onCancel: () => void;
}

export function MergePlanConfirmation({
  mergePlan,
  pdfUrl,
  onConfirm,
  onCancel,
}: MergePlanConfirmationProps) {
  // Initialize editable groups from merge plan
  const [groups, setGroups] = useState<EditableGroup[]>(() => {
    const mergeGroups = mergePlan?.mergeGroups || [];
    return mergeGroups.map(g => ({
      ...g,
      isModified: false,
    }));
  });

  // Track active drag item
  const [activeId, setActiveId] = useState<string | null>(null);

  // PDF viewer state
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [numPages, setNumPages] = useState<number>(0);
  const [scale, setScale] = useState(1.0);

  // Get page ranges and categories from merge plan
  const { pageRanges, tableCategories } = useMemo(() => {
    const ranges: { [tableId: string]: { start: number; end: number } } = {};
    const categories: { [tableId: string]: string } = {};

    const mergeGroups = mergePlan?.mergeGroups || [];
    mergeGroups.forEach(group => {
      if (group.pageRanges) {
        Object.assign(ranges, group.pageRanges);
      }
      if (group.tableCategories) {
        Object.assign(categories, group.tableCategories);
      }
    });

    return { pageRanges: ranges, tableCategories: categories };
  }, [mergePlan.mergeGroups]);

  // Find active item details for overlay
  const activeItem = useMemo(() => {
    if (!activeId) return null;
    for (const group of groups) {
      if (group.tableIds.includes(activeId)) {
        return {
          tableId: activeId,
          pageRange: pageRanges[activeId],
          category: tableCategories[activeId],
        };
      }
    }
    return null;
  }, [activeId, groups, pageRanges, tableCategories]);

  // Drag-and-drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  // Handle drag start
  const handleDragStart = (event: DragStartEvent) => {
    setActiveId(event.active.id as string);
  };

  // Handle drag over (for visual feedback)
  const handleDragOver = (event: DragOverEvent) => {
    // Visual feedback is handled by the droppable components
  };

  // Handle drag end - move table between groups
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);

    if (!over) return;

    const activeTableId = active.id as string;
    const overId = over.id as string;

    // Find source group
    const sourceGroupIndex = groups.findIndex(g => g.tableIds.includes(activeTableId));
    if (sourceGroupIndex === -1) return;

    // Determine destination group
    let destGroupIndex: number;

    if (overId.startsWith('group-')) {
      // Dropped on group droppable area
      const groupId = overId.replace('group-', '');
      destGroupIndex = groups.findIndex(g => g.id === groupId);
    } else {
      // Dropped on another table - find its group
      destGroupIndex = groups.findIndex(g => g.tableIds.includes(overId));
    }

    if (destGroupIndex === -1 || sourceGroupIndex === destGroupIndex) return;

    // Move table from source to destination
    setGroups(prevGroups => {
      const newGroups = prevGroups.map((group, idx) => {
        if (idx === sourceGroupIndex) {
          // Remove from source
          return {
            ...group,
            tableIds: group.tableIds.filter(id => id !== activeTableId),
            isModified: true,
          };
        }
        if (idx === destGroupIndex) {
          // Add to destination
          return {
            ...group,
            tableIds: [...group.tableIds, activeTableId],
            isModified: true,
          };
        }
        return group;
      });
      return newGroups;
    });
  };

  // Create new empty group
  const handleCreateGroup = () => {
    const newGroupId = `MG-NEW-${Date.now()}`;
    const newGroup: EditableGroup = {
      id: newGroupId,
      tableIds: [],
      mergeType: 'user_created',
      decisionLevel: 0,
      confidence: 1.0,
      reasoning: 'User-created group for custom table arrangement',
      confirmed: null,
      userOverride: null,
      isModified: true,
    };
    setGroups([...groups, newGroup]);
  };

  // Delete empty group
  const handleDeleteGroup = (groupId: string) => {
    setGroups(prevGroups => prevGroups.filter(g => g.id !== groupId));
  };

  // Build confirmation payload
  const handleConfirm = () => {
    const confirmedGroups: ConfirmedGroup[] = groups
      .filter(g => g.tableIds.length > 0)
      .map(g => ({
        id: g.id,
        tableIds: g.tableIds,
        confirmed: true,
        userOverride: g.isModified ? {
          action: 'merge' as const,
          newGroups: [{ tableIds: g.tableIds }],
          reason: 'User modified group via drag-and-drop',
        } : undefined,
      }));

    onConfirm({ confirmedGroups });
  };

  // Calculate statistics
  const stats = useMemo(() => {
    const nonEmptyGroups = groups.filter(g => g.tableIds.length > 0);
    const modifiedCount = groups.filter(g => g.isModified).length;
    const totalTables = groups.reduce((sum, g) => sum + g.tableIds.length, 0);
    return {
      groupCount: nonEmptyGroups.length,
      modifiedCount,
      totalTables,
    };
  }, [groups]);

  // PDF handlers
  const handlePageClick = (page: number) => {
    if (pdfUrl) {
      setSelectedPage(page);
    }
  };

  const handleDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
  };

  const handleClosePdf = () => {
    setSelectedPage(null);
  };

  const handleZoomIn = () => {
    setScale(prev => Math.min(prev + 0.25, 2.5));
  };

  const handleZoomOut = () => {
    setScale(prev => Math.max(prev - 0.25, 0.5));
  };

  const handlePrevPage = () => {
    if (selectedPage && selectedPage > 1) {
      setSelectedPage(selectedPage - 1);
    }
  };

  const handleNextPage = () => {
    if (selectedPage && selectedPage < numPages) {
      setSelectedPage(selectedPage + 1);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Layers className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-800">Confirm Merge Plan</h2>
              <p className="text-sm text-gray-500">
                Review and adjust how SOA tables will be grouped for interpretation
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={onCancel}>
              <X className="w-4 h-4 mr-2" />
              Cancel
            </Button>
            <Button onClick={handleConfirm}>
              <Check className="w-4 h-4 mr-2" />
              Confirm & Start Interpretation
            </Button>
          </div>
        </div>

        {/* Statistics Bar */}
        <div className="flex items-center gap-4 mt-4 text-sm">
          <Badge variant="secondary" className="gap-1">
            <span className="text-gray-500">Tables:</span>
            <span className="font-semibold">{stats.totalTables}</span>
          </Badge>
          <Badge variant="secondary" className="gap-1">
            <span className="text-gray-500">Groups:</span>
            <span className="font-semibold">{stats.groupCount}</span>
          </Badge>
          {stats.modifiedCount > 0 && (
            <Badge variant="outline" className="gap-1 bg-yellow-50 text-yellow-700 border-yellow-200">
              <AlertTriangle className="w-3 h-3" />
              <span>{stats.modifiedCount} modified</span>
            </Badge>
          )}
        </div>
      </div>

      {/* Split Panel Layout */}
      <PanelGroup direction="horizontal" className="flex-1">
        {/* Left Panel - Merge Plan Content */}
        <Panel defaultSize={selectedPage ? 60 : 100} minSize={40}>
          <div className="flex flex-col h-full">
            {/* Instructions */}
            <div className="px-6 py-3 bg-blue-50 border-b border-blue-100">
              <div className="flex items-center gap-2 text-sm text-blue-700">
                <Info className="w-4 h-4" />
                <span>
                  Drag tables between groups to reorganize. Tables in the same group will be merged
                  and processed together through the 12-stage interpretation pipeline.
                  {pdfUrl && <span className="ml-1 font-medium">Click page numbers to view the PDF.</span>}
                </span>
              </div>
            </div>

            {/* Drag-and-drop area */}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
            >
              <ScrollArea className="flex-1">
                <div className="p-6">
                  <div className={cn(
                    "grid gap-4",
                    selectedPage
                      ? "grid-cols-1 md:grid-cols-2"
                      : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
                  )}>
                    {groups.map(group => (
                      <MergeGroupCard
                        key={group.id}
                        group={group}
                        pageRanges={pageRanges}
                        tableCategories={tableCategories}
                        onDeleteGroup={
                          group.tableIds.length === 0
                            ? () => handleDeleteGroup(group.id)
                            : undefined
                        }
                        isNewGroup={group.id.startsWith('MG-NEW-')}
                        onPageClick={pdfUrl ? handlePageClick : undefined}
                      />
                    ))}

                    {/* Create new group button */}
                    <button
                      onClick={handleCreateGroup}
                      className={cn(
                        "flex flex-col items-center justify-center gap-2 p-6",
                        "border-2 border-dashed border-gray-300 rounded-lg",
                        "text-gray-500 hover:text-gray-700 hover:border-gray-400",
                        "hover:bg-gray-50 transition-all min-h-[180px]"
                      )}
                    >
                      <Plus className="w-8 h-8" />
                      <span className="text-sm font-medium">Create New Group</span>
                    </button>
                  </div>
                </div>
              </ScrollArea>

              {/* Drag overlay - Enhanced with scale and shadow */}
              <DragOverlay
                dropAnimation={{
                  duration: 200,
                  easing: 'cubic-bezier(0.18, 0.67, 0.6, 1.22)',
                }}
              >
                {activeItem && (
                  <div className="drag-item-active">
                    <TableItemOverlay
                      tableId={activeItem.tableId}
                      pageRange={activeItem.pageRange}
                      category={activeItem.category}
                    />
                  </div>
                )}
              </DragOverlay>
            </DndContext>
          </div>
        </Panel>

        {/* Right Panel - PDF Viewer (shown when page is selected) */}
        {selectedPage && pdfUrl && (
          <>
            <PanelResizeHandle className="w-2 bg-gray-200 hover:bg-gray-300 transition-colors cursor-col-resize" />
            <Panel defaultSize={40} minSize={30}>
              <div className="flex flex-col h-full bg-gray-100 border-l border-gray-200">
                {/* PDF Viewer Header */}
                <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-gray-500" />
                    <span className="text-sm font-medium text-gray-700">
                      Page {selectedPage} of {numPages}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    {/* Navigation */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handlePrevPage}
                      disabled={selectedPage <= 1}
                      className="h-8 w-8 p-0"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleNextPage}
                      disabled={selectedPage >= numPages}
                      className="h-8 w-8 p-0"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                    <div className="w-px h-4 bg-gray-300 mx-1" />
                    {/* Zoom */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleZoomOut}
                      disabled={scale <= 0.5}
                      className="h-8 w-8 p-0"
                    >
                      <ZoomOut className="w-4 h-4" />
                    </Button>
                    <span className="text-xs text-gray-500 w-12 text-center">
                      {Math.round(scale * 100)}%
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleZoomIn}
                      disabled={scale >= 2.5}
                      className="h-8 w-8 p-0"
                    >
                      <ZoomIn className="w-4 h-4" />
                    </Button>
                    <div className="w-px h-4 bg-gray-300 mx-1" />
                    {/* Close */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleClosePdf}
                      className="h-8 w-8 p-0 text-gray-500 hover:text-gray-700"
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                </div>

                {/* PDF Content */}
                <ScrollArea className="flex-1">
                  <div className="flex justify-center p-4">
                    <Document
                      file={pdfUrl}
                      onLoadSuccess={handleDocumentLoadSuccess}
                      loading={
                        <div className="flex items-center justify-center h-64">
                          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                        </div>
                      }
                      error={
                        <div className="flex flex-col items-center justify-center h-64 text-gray-500">
                          <AlertTriangle className="w-8 h-8 mb-2" />
                          <p className="text-sm">Failed to load PDF</p>
                        </div>
                      }
                    >
                      <Page
                        pageNumber={selectedPage}
                        scale={scale}
                        renderTextLayer={false}
                        renderAnnotationLayer={false}
                        className="shadow-lg"
                      />
                    </Document>
                  </div>
                </ScrollArea>
              </div>
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
}
