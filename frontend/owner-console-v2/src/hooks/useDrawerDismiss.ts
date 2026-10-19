import { useEffect, useRef } from 'react';

export interface DrawerStackItem {
  id: string;
  onClose: () => void;
  triggerElement: HTMLElement | null;
}

// Global ordered stack of active drawers (topmost is at the end)
export const drawerStack: DrawerStackItem[] = [];
let isGlobalListenerActive = false;

export function handleDrawerGlobalKeyDown(e: KeyboardEvent): boolean {
  if (e.key !== 'Escape' || e.defaultPrevented) return false;
  if (drawerStack.length === 0) return false;

  // Prevent default and stop propagation so parent drawers or background handlers do not fire
  e.preventDefault();
  e.stopPropagation();

  // Pop only the topmost active drawer
  const topmost = drawerStack.pop();
  if (topmost) {
    topmost.onClose();
    const el = topmost.triggerElement;
    if (el && typeof el.focus === 'function') {
      setTimeout(() => {
        try {
          if (typeof document !== 'undefined' && document.contains(el)) {
            el.focus();
          }
        } catch {
          // ignore if unmounted
        }
      }, 0);
    }
    return true;
  }
  return false;
}

export function ensureDrawerGlobalListener() {
  if (!isGlobalListenerActive && typeof window !== 'undefined') {
    window.addEventListener('keydown', handleDrawerGlobalKeyDown, true); // capture phase
    isGlobalListenerActive = true;
  }
}

export interface UseDrawerDismissOptions {
  isOpen: boolean;
  onClose: () => void;
  drawerId: string;
}

export function useDrawerDismiss({ isOpen, onClose, drawerId }: UseDrawerDismissOptions) {
  const triggerElementRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    ensureDrawerGlobalListener();

    if (isOpen) {
      // Capture element that had focus before opening
      if (typeof document !== 'undefined' && document.activeElement instanceof HTMLElement) {
        triggerElementRef.current = document.activeElement;
      }

      // Add to stack if not already present
      if (!drawerStack.some((d) => d.id === drawerId)) {
        drawerStack.push({
          id: drawerId,
          onClose: () => onCloseRef.current(),
          get triggerElement() {
            return triggerElementRef.current;
          },
        });
      }

      return () => {
        // Remove from stack on close or unmount
        const index = drawerStack.findIndex((d) => d.id === drawerId);
        if (index !== -1) {
          const [removed] = drawerStack.splice(index, 1);
          const el = removed?.triggerElement;
          if (el && typeof el.focus === 'function') {
            setTimeout(() => {
              try {
                if (typeof document !== 'undefined' && document.contains(el)) {
                  el.focus();
                }
              } catch {
                // ignore
              }
            }, 0);
          }
        }
      };
    }
  }, [isOpen, drawerId]);
}
