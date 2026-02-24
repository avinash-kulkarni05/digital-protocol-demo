import { useState, useRef } from "react";
import { Drawer as DrawerPrimitive } from "vaul";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { Loader2, X, Paperclip } from "lucide-react";

interface AddObservationDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function getTodayDate(): string {
  return new Date().toISOString().split("T")[0];
}

export function AddObservationDrawer({ open, onOpenChange }: AddObservationDrawerProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  const resetForm = () => {
    setName("");
    setDescription("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    if (!name.trim() || !description.trim()) {
      toast({
        title: "Validation Error",
        description: "Title and Description are required.",
        variant: "destructive",
      });
      return;
    }

    setSaving(true);
    try {
      await api.observations.create({
        name: name.trim(),
        description: description.trim(),
        date: getTodayDate(),
        files: files.length > 0 ? files : undefined,
      });
      toast({
        title: "Observation Saved",
        description: "Your observation has been saved to Notion.",
      });
      resetForm();
      onOpenChange(false);
    } catch (error: any) {
      toast({
        title: "Error",
        description: error.message || "Failed to save observation.",
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <DrawerPrimitive.Root direction="right" open={open} onOpenChange={onOpenChange}>
      <DrawerPrimitive.Portal>
        <DrawerPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80" />
        <DrawerPrimitive.Content
          className="fixed inset-y-0 right-0 z-50 flex h-full w-[400px] flex-col border-l bg-white"
          style={{ maxWidth: "90vw" }}
        >
          <div className="flex flex-col h-full">
            <div className="border-b border-gray-200 px-6 py-4 flex items-start justify-between">
              <div>
                <DrawerPrimitive.Title className="text-lg font-semibold text-gray-900">
                  Add Observation
                </DrawerPrimitive.Title>
                <DrawerPrimitive.Description className="text-sm text-gray-500 mt-1">
                  Fill in the details below and save to Notion.
                </DrawerPrimitive.Description>
              </div>
              <button
                onClick={() => onOpenChange(false)}
                className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
              <div className="space-y-2">
                <Label htmlFor="obs-name" className="text-sm font-medium text-gray-700">
                  Title <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="obs-name"
                  placeholder="Enter Title"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={saving}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="obs-description" className="text-sm font-medium text-gray-700">
                  Description <span className="text-red-500">*</span>
                </Label>
                <Textarea
                  id="obs-description"
                  placeholder="Enter description"
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={saving}
                />
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-medium text-gray-700">
                  Attachments
                </Label>
                <div
                  className="flex items-center gap-3 w-full rounded-md border border-dashed border-gray-300 px-3 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Paperclip className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <span className="text-sm text-gray-500">
                    Click to attach files (optional)
                  </span>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={handleFileChange}
                  disabled={saving}
                />
                {files.length > 0 && (
                  <div className="space-y-1.5 mt-2">
                    {files.map((f, i) => (
                      <div
                        key={`${f.name}-${i}`}
                        className="flex items-center gap-2 text-sm bg-gray-50 rounded-md px-3 py-1.5"
                      >
                        <Paperclip className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                        <span className="truncate flex-1 text-gray-700">{f.name}</span>
                        <button
                          type="button"
                          onClick={() => removeFile(i)}
                          className="p-0.5 rounded text-gray-400 hover:text-gray-600"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-gray-200 px-6 py-4 flex gap-3">
              <Button onClick={handleSave} disabled={saving} className="flex-1">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {saving ? "Saving..." : "Save"}
              </Button>
              <DrawerPrimitive.Close asChild>
                <Button variant="outline" disabled={saving} className="flex-1">
                  Cancel
                </Button>
              </DrawerPrimitive.Close>
            </div>
          </div>
        </DrawerPrimitive.Content>
      </DrawerPrimitive.Portal>
    </DrawerPrimitive.Root>
  );
}
