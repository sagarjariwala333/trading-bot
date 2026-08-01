import React from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function Dialog({
  open,
  onClose,
  title,
  description,
  type = 'confirm', // 'confirm' or 'alert'
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'destructive', // 'destructive', 'warning', 'info'
  onConfirm
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-md bg-white dark:bg-[#0d1220] border border-slate-200 dark:border-white/[0.1] rounded-2xl shadow-2xl overflow-hidden p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-150">
        
        {/* Header */}
        <div className="flex items-start gap-3.5">
          <div className={cn(
            "p-3 rounded-xl text-xl shrink-0 flex items-center justify-center",
            variant === 'destructive' ? "bg-red-500/10 text-red-500 border border-red-500/20" :
            variant === 'warning' ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" :
            "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
          )}>
            {variant === 'destructive' ? '🛑' : variant === 'warning' ? '⚠️' : 'ℹ️'}
          </div>
          
          <div className="flex flex-col gap-1">
            <h3 className="text-lg font-extrabold text-slate-900 dark:text-white leading-snug tracking-tight">
              {title}
            </h3>
            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {description}
            </p>
          </div>
        </div>

        {/* Action Footer */}
        <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-200 dark:border-white/[0.06] mt-2">
          {type === 'confirm' && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="text-xs font-semibold px-4 py-2 h-auto border-slate-300 dark:border-slate-700 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg"
            >
              {cancelText}
            </Button>
          )}

          <Button
            size="sm"
            onClick={() => {
              if (onConfirm) onConfirm();
              onClose();
            }}
            className={cn(
              "text-xs font-bold px-4 py-2 h-auto rounded-lg text-white shadow-md transition-all",
              variant === 'destructive' ? "bg-red-600 hover:bg-red-500 shadow-red-500/20" :
              variant === 'warning' ? "bg-amber-600 hover:bg-amber-500 shadow-amber-500/20" :
              "bg-indigo-600 hover:bg-indigo-500 shadow-indigo-500/20"
            )}
          >
            {type === 'confirm' ? confirmText : 'OK'}
          </Button>
        </div>

      </div>
    </div>
  );
}
