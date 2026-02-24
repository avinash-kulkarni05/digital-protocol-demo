import { useState } from 'react';
import { useDroppable } from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Trash2, Layers, Split, Copy, Inbox, ArrowDown, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';
import { SortableTableItem } from './SortableTableItem';
import { ConfidenceIndicator, ConfidenceBadge } from './ConfidenceIndicator';
import type { MergeGroup } from '@/lib/api';

interface MergeGroupCardProps {
  group: MergeGroup & { isModified?: boolean };
  pageRanges?: { [tableId: string]: { start: number; end: number } };
  tableCategories?: { [tableId: string]: string };
  onDeleteGroup?: () => void;
  isNewGroup?: boolean;
  onPageClick?: (page: number) => void;
}

function getDecisionBadgeVariant(decision: string) {
  switch (decision) {
    case 'SUGGEST_MERGE':
      return 'bg-green-100 text-green-700 border-green-300';
    case 'KEEP_SEPARATE':
      return 'bg-red-100 text-red-700 border-red-300';
    case 'CONTINUE':
      return 'bg-blue-100 text-blue-700 border-blue-300';
    default:
      return 'bg-gray-100 text-gray-700 border-gray-300';
  }
}

function formatEvidenceKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function formatEvidenceValue(value: any): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : `${(value * 100).toFixed(1)}%`;
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  return String(value);
}

export function MergeGroupCard({
  group,
  pageRanges = {},
  tableCategories = {},
  onDeleteGroup,
  isNewGroup = false,
  onPageClick,
}: MergeGroupCardProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const { setNodeRef, isOver } = useDroppable({
    id: `group-${group.id}`,
    data: {
      type: 'group',
      groupId: group.id,
    },
  });

  const getMergeTypeLabel = (mergeType: string) => {
    switch (mergeType) {
      case 'physical_continuation':
        return 'Continuation';
      case 'same_schedule':
        return 'Same Schedule';
      case 'standalone':
        return 'Standalone';
      case 'user_created':
        return 'Custom';
      default:
        return mergeType.replace(/_/g, ' ');
    }
  };

  const getMergeTypeIcon = (mergeType: string) => {
    switch (mergeType) {
      case 'physical_continuation':
        return <ArrowDown className="w-3 h-3" />;
      case 'same_schedule':
        return <Copy className="w-3 h-3" />;
      case 'standalone':
        return <Split className="w-3 h-3" />;
      default:
        return <Layers className="w-3 h-3" />;
    }
  };

  const getMergeTypeColor = (mergeType: string) => {
    switch (mergeType) {
      case 'physical_continuation':
        return 'text-blue-600';
      case 'same_schedule':
        return 'text-purple-600';
      case 'standalone':
        return 'text-gray-600';
      case 'user_created':
        return 'text-amber-600';
      default:
        return 'text-gray-500';
    }
  };

  const hasDecisionPath = group.decisionPath && group.decisionPath.length > 0;

  return (
    <Card
      ref={setNodeRef}
      className={cn(
        "transition-all duration-200",
        isOver && "ring-2 ring-primary bg-primary/5",
        group.isModified && "border-yellow-400 bg-yellow-50/30",
        isNewGroup && "border-dashed border-2 border-gray-300"
      )}
    >
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-semibold">{group.id}</CardTitle>
            {group.isModified && (
              <Badge variant="outline" className="text-[10px] bg-yellow-100 text-yellow-700 border-yellow-300">
                Modified
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            <ConfidenceIndicator
              confidence={group.confidence}
              reasoning={group.reasoning}
              size="sm"
            />
            {onDeleteGroup && group.tableIds.length === 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-gray-400 hover:text-red-500"
                onClick={onDeleteGroup}
              >
                <Trash2 className="w-3 h-3" />
              </Button>
            )}
          </div>
        </div>
        <div className={cn("flex items-center gap-1.5 text-xs", getMergeTypeColor(group.mergeType))}>
          {getMergeTypeIcon(group.mergeType)}
          <span className="font-medium">{getMergeTypeLabel(group.mergeType)}</span>
          {group.decisionLevel > 0 && (
            <span className="ml-1 text-gray-400 font-normal">
              (Level {group.decisionLevel})
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="px-4 py-2">
        <SortableContext
          items={group.tableIds}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-2 min-h-[60px]">
            {group.tableIds.map(tableId => (
              <SortableTableItem
                key={tableId}
                tableId={tableId}
                pageRange={pageRanges[tableId] || group.pageRanges?.[tableId]}
                category={tableCategories[tableId] || group.tableCategories?.[tableId]}
                onPageClick={onPageClick}
              />
            ))}

            {group.tableIds.length === 0 && (
              <div className={cn(
                "flex flex-col items-center justify-center h-[80px] rounded-lg border-2 border-dashed p-4 transition-all",
                isOver ? "border-primary bg-primary/5 drop-zone-active" : "border-gray-200 bg-gray-50/50"
              )}>
                <Inbox className={cn(
                  "w-5 h-5 mb-1.5 transition-colors",
                  isOver ? "text-primary" : "text-gray-300"
                )} />
                <p className={cn(
                  "text-xs text-center transition-colors",
                  isOver ? "text-primary font-medium" : "text-gray-400"
                )}>
                  {isOver ? "Release to add table" : "Drop tables here"}
                </p>
              </div>
            )}
          </div>
        </SortableContext>
      </CardContent>

      <CardFooter className="px-4 pb-3 pt-0 flex flex-col items-stretch gap-0">
        <p className="text-xs text-gray-500">{group.reasoning}</p>

        {hasDecisionPath && (
          <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen}>
            <CollapsibleTrigger asChild>
              <button
                className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600 mt-1.5 transition-colors"
              >
                {detailsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                <span>Supporting Evidence</span>
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-2 space-y-2">
                {group.decisionPath!.map((step, idx) => {
                  // Filter out internal keys (starting with _) from evidence
                  const visibleEvidence = step.evidence
                    ? Object.entries(step.evidence).filter(([key]) => !key.startsWith('_'))
                    : [];

                  return (
                    <div
                      key={idx}
                      className="rounded-md border border-gray-100 bg-gray-50/50 p-2"
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-[11px] font-medium text-gray-700">{step.name}</span>
                        <ConfidenceBadge confidence={step.confidence} className="text-[9px]" />
                      </div>
                      {visibleEvidence.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                          {visibleEvidence.map(([key, value]) => (
                            <span key={key} className="text-[10px] text-gray-400">
                              <span className="font-medium">{formatEvidenceKey(key)}:</span>{' '}
                              {formatEvidenceValue(value)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardFooter>
    </Card>
  );
}
