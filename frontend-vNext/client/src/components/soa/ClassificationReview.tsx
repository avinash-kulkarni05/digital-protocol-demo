import { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Brain, Check, X, Pencil, AlertTriangle, BarChart3, Tag } from 'lucide-react';
import type { ClassificationReviewData, ClassificationProfile } from '@/lib/api';

interface ClassificationReviewProps {
  classificationData: ClassificationReviewData;
  onConfirm: (confirmedProfiles: Record<string, ClassificationProfile>) => void;
  onCancel: () => void;
}

function confidenceTier(c: number): 'high' | 'medium' | 'low' {
  if (c >= 0.8) return 'high';
  if (c >= 0.5) return 'medium';
  return 'low';
}

const tierColors = {
  high:   { border: 'border-l-green-400', bar: '[&>div]:bg-green-500', track: 'bg-green-100', text: 'text-green-700', dot: 'bg-green-500', label: 'High' },
  medium: { border: 'border-l-amber-400', bar: '[&>div]:bg-amber-500', track: 'bg-amber-100', text: 'text-amber-700', dot: 'bg-amber-500', label: 'Medium' },
  low:    { border: 'border-l-red-400',   bar: '[&>div]:bg-red-500',   track: 'bg-red-100',   text: 'text-red-700',   dot: 'bg-red-500',   label: 'Low' },
} as const;

export function ClassificationReview({
  classificationData,
  onConfirm,
  onCancel,
}: ClassificationReviewProps) {
  const groups = classificationData.groups || {};
  const groupIds = Object.keys(groups);

  // Sort by confidence ascending so low-confidence items appear first
  const sortedGroupIds = [...groupIds].sort(
    (a, b) => groups[a].confidence - groups[b].confidence
  );

  // Track only the editable field: tableStructureType per group
  const [editedTypes, setEditedTypes] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState<string | null>(null);

  const getDisplayType = (groupId: string) =>
    editedTypes[groupId] ?? groups[groupId].tableStructureType;

  const isModified = (groupId: string) =>
    groupId in editedTypes && editedTypes[groupId] !== groups[groupId].tableStructureType;

  // Aggregate statistics
  const stats = useMemo(() => {
    const profiles = Object.values(groups);
    const total = profiles.length;
    if (total === 0) return { avg: 0, high: 0, medium: 0, low: 0, failed: 0 };

    const avg = profiles.reduce((s, p) => s + p.confidence, 0) / total;
    const high = profiles.filter(p => p.confidence >= 0.8).length;
    const medium = profiles.filter(p => p.confidence >= 0.5 && p.confidence < 0.8).length;
    const low = profiles.filter(p => p.confidence < 0.5).length;
    const failed = profiles.filter(p => p.tableStructureType === 'classification_failed').length;
    return { avg, high, medium, low, failed };
  }, [groups]);

  const editedCount = useMemo(
    () => groupIds.filter(id => isModified(id)).length,
    [editedTypes, groups]
  );

  const handleConfirm = () => {
    const confirmed: Record<string, ClassificationProfile> = {};
    for (const [groupId, profile] of Object.entries(groups)) {
      confirmed[groupId] = {
        ...profile,
        tableStructureType: getDisplayType(groupId),
        userModified: isModified(groupId),
      };
    }
    onConfirm(confirmed);
  };

  return (
    <TooltipProvider delayDuration={300}>
      <div className="flex flex-col h-full">
        {/* ── Zone A: Header + Summary Strip ── */}
        <div className="-mx-6 -mt-6 bg-gradient-to-b from-gray-50 to-white px-6 pt-5 pb-4 border-b border-gray-100">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-gray-900 flex items-center justify-center shrink-0">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sf-headline text-gray-900 font-semibold">
                Table Classification
              </h2>
              <p className="text-sf-footnote text-muted-foreground mt-0.5">
                Review AI classifications below. Click a type to edit. Low-confidence items shown first.
              </p>
            </div>
          </div>

          {/* Summary strip */}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            {/* Average confidence */}
            <div className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-md px-2.5 py-1 shadow-sm">
              <BarChart3 className="w-3.5 h-3.5 text-gray-500" />
              <span className="text-xs font-medium text-gray-700">
                Avg: {(stats.avg * 100).toFixed(0)}%
              </span>
            </div>

            {/* Distribution dots */}
            {stats.high > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                {stats.high} high
              </div>
            )}
            {stats.medium > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                {stats.medium} medium
              </div>
            )}
            {stats.low > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-gray-600">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                {stats.low} low
              </div>
            )}

            {/* Failed alert */}
            {stats.failed > 0 && (
              <div className="flex items-center gap-1 text-xs text-red-600 font-medium ml-auto">
                <AlertTriangle className="w-3.5 h-3.5" />
                {stats.failed} failed
              </div>
            )}
          </div>
        </div>

        {/* ── Zone B: Card List ── */}
        <ScrollArea className="flex-1 -mx-6" style={{ maxHeight: 'calc(80vh - 200px)' }}>
          <div className="px-6 py-4 space-y-3">
            {sortedGroupIds.map((groupId, idx) => {
              const profile = groups[groupId];
              const displayType = getDisplayType(groupId);
              const modified = isModified(groupId);
              const isEditing = editingId === groupId;
              const failed = profile.tableStructureType === 'classification_failed';
              const tier = confidenceTier(profile.confidence);
              const colors = tierColors[tier];
              const pct = Math.round(profile.confidence * 100);

              return (
                <Card
                  key={groupId}
                  className={cn(
                    'group border-l-[3px] shadow-sm transition-all hover:shadow-md animate-fade-in',
                    colors.border,
                    failed && 'bg-red-50/40'
                  )}
                  style={{ animationDelay: `${idx * 60}ms`, animationFillMode: 'both' }}
                >
                  <CardContent className="p-4">
                    {/* Top section: name + classification + confidence */}
                    <div className="flex items-start gap-4">
                      {/* Left: group name & classification type */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900 truncate">
                            {groupId}
                          </span>
                          {modified && (
                            <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200 shrink-0 px-1.5 py-0">
                              edited
                            </Badge>
                          )}
                        </div>

                        {/* Classification type — inline editable */}
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <Tag className="w-3 h-3 text-gray-400 shrink-0" />
                          {isEditing ? (
                            <Input
                              autoFocus
                              value={displayType}
                              onChange={(e) => setEditedTypes(prev => ({ ...prev, [groupId]: e.target.value }))}
                              onBlur={() => setEditingId(null)}
                              onKeyDown={(e) => { if (e.key === 'Enter') setEditingId(null); }}
                              className="h-6 text-xs flex-1 px-1.5"
                            />
                          ) : (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  className={cn(
                                    'text-xs truncate text-left transition-colors',
                                    failed ? 'text-red-600 italic' : 'text-gray-500 hover:text-purple-700'
                                  )}
                                  onClick={() => setEditingId(groupId)}
                                >
                                  {displayType}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="top">Click to edit</TooltipContent>
                            </Tooltip>
                          )}
                          {!isEditing && !modified && (
                            <Pencil
                              className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer shrink-0"
                              onClick={() => setEditingId(groupId)}
                            />
                          )}
                        </div>
                      </div>

                      {/* Right: confidence block */}
                      <div className="w-[100px] shrink-0 text-right">
                        <span className={cn('text-lg font-bold tabular-nums', colors.text)}>
                          {pct}%
                        </span>
                        <Progress
                          value={pct}
                          className={cn('h-1.5 mt-1', colors.track, colors.bar)}
                        />
                        <span className={cn('text-[10px] font-medium mt-0.5 block', colors.text)}>
                          {colors.label}
                        </span>
                      </div>
                    </div>

                    {/* Bottom section: characteristics pills */}
                    {profile.characteristics?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-100">
                        {profile.characteristics.map((c, i) => (
                          <span
                            key={i}
                            className="text-[11px] text-muted-foreground bg-gray-50 border border-gray-200/60 px-2 py-0.5 rounded-full"
                          >
                            {c}
                          </span>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </ScrollArea>

        {/* ── Zone C: Footer ── */}
        <div className="-mx-6 -mb-6 border-t border-gray-100 px-6 py-3 flex items-center justify-between backdrop-blur-sm bg-white/90">
          <span className="text-xs text-muted-foreground">
            {editedCount > 0
              ? `${editedCount} classification${editedCount !== 1 ? 's' : ''} edited`
              : `${groupIds.length} table${groupIds.length !== 1 ? 's' : ''} ready for review`}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onCancel}>
              <X className="w-3.5 h-3.5 mr-1" />
              Back
            </Button>
            <Button size="sm" onClick={handleConfirm}>
              <Check className="w-3.5 h-3.5 mr-1" />
              Confirm & Interpret
            </Button>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
