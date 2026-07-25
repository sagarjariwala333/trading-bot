import { Alert, AlertDescription, AlertAction } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

export default function AlertBanner({ errorMsg, successMsg, onDismissError, onDismissSuccess }) {
  return (
    <>
      {errorMsg && (
        <Alert variant="destructive" className="border-red-500/30 bg-red-500/10 text-red-300">
          <AlertDescription className="text-red-300 font-medium">⚠️ {errorMsg}</AlertDescription>
          <AlertAction>
            <Button size="sm" variant="ghost" onClick={onDismissError}
              className="text-red-300 hover:text-red-200 hover:bg-red-500/20 h-6 px-2 text-xs">
              Dismiss
            </Button>
          </AlertAction>
        </Alert>
      )}
      {successMsg && (
        <Alert className="border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
          <AlertDescription className="text-emerald-300 font-medium">✅ {successMsg}</AlertDescription>
          <AlertAction>
            <Button size="sm" variant="ghost" onClick={onDismissSuccess}
              className="text-emerald-300 hover:text-emerald-200 hover:bg-emerald-500/20 h-6 px-2 text-xs">
              Dismiss
            </Button>
          </AlertAction>
        </Alert>
      )}
    </>
  );
}
