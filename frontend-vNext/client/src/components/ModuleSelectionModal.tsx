import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Loader2, Play } from "lucide-react";
import { api, type ModuleInfo } from "@/lib/api";

interface ModuleSelectionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStartExtraction: (modules: string[]) => void;
  isStarting?: boolean;
}

const WAVE_LABELS: Record<number, string> = {
  0: "Foundation",
  1: "Core Modules",
  2: "Dependent Modules",
};

export default function ModuleSelectionModal({
  open,
  onOpenChange,
  onStartExtraction,
  isStarting = false,
}: ModuleSelectionModalProps) {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open && modules.length === 0) {
      setLoading(true);
      api.extraction.getModules()
        .then((data) => {
          setModules(data);
          // Select all enabled modules by default
          setSelected(new Set(data.filter((m) => m.enabled).map((m) => m.module_id)));
        })
        .catch((err) => console.error("Failed to load modules:", err))
        .finally(() => setLoading(false));
    }
  }, [open, modules.length]);

  const toggleModule = (moduleId: string) => {
    // study_metadata is always required
    if (moduleId === "study_metadata") return;

    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(moduleId)) {
        next.delete(moduleId);
      } else {
        next.add(moduleId);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(modules.filter((m) => m.enabled).map((m) => m.module_id)));
  };

  const deselectAll = () => {
    // Always keep study_metadata
    setSelected(new Set(["study_metadata"]));
  };

  const handleStart = () => {
    onStartExtraction(Array.from(selected));
  };

  // Group modules by wave
  const groupedModules = modules.reduce((acc, mod) => {
    const wave = mod.wave;
    if (!acc[wave]) acc[wave] = [];
    acc[wave].push(mod);
    return acc;
  }, {} as Record<number, ModuleInfo[]>);

  const selectedCount = selected.size;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Custom Extract</DialogTitle>
          <DialogDescription>
            Select which modules to extract. Study Metadata is always included as a foundation.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {/* Select/Deselect All */}
            <div className="flex gap-3">
              <Button variant="outline" size="sm" onClick={selectAll} className="text-xs">
                Select All
              </Button>
              <Button variant="outline" size="sm" onClick={deselectAll} className="text-xs">
                Deselect All
              </Button>
            </div>

            {/* Module Groups */}
            {Object.entries(groupedModules)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([wave, mods]) => (
                <div key={wave}>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    {WAVE_LABELS[Number(wave)] || `Wave ${wave}`}
                  </h4>
                  <div className="space-y-2">
                    {mods.map((mod) => {
                      const isStudyMetadata = mod.module_id === "study_metadata";
                      const isChecked = selected.has(mod.module_id);

                      return (
                        <div
                          key={mod.module_id}
                          className="flex items-center gap-3 py-1.5 px-2 rounded-md hover:bg-gray-50 transition-colors"
                        >
                          <Checkbox
                            id={`mod-${mod.module_id}`}
                            checked={isChecked}
                            onCheckedChange={() => toggleModule(mod.module_id)}
                            disabled={isStudyMetadata || !mod.enabled}
                          />
                          <Label
                            htmlFor={`mod-${mod.module_id}`}
                            className={`text-sm cursor-pointer flex-1 ${
                              !mod.enabled ? "text-gray-400" : ""
                            }`}
                          >
                            {mod.display_name}
                            {isStudyMetadata && (
                              <span className="ml-2 text-xs text-gray-400">(always required)</span>
                            )}
                            {!mod.enabled && (
                              <span className="ml-2 text-xs text-gray-400">(disabled)</span>
                            )}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
          </div>
        )}

        <div className="flex justify-end pt-2 border-t">
          <Button
            onClick={handleStart}
            disabled={isStarting || selectedCount === 0}
            className="rounded-full px-6"
          >
            {isStarting ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Start Extraction ({selectedCount} selected)
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
