import * as React from "react";

interface NavLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  onNavigate: () => void;
}

function isPlainLeftClick(event: React.MouseEvent): boolean {
  return event.button === 0
    && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
    && !event.defaultPrevented;
}

// Real anchor for in-app routes: unmodified primary clicks move through
// History without a reload, while modified clicks keep native new-tab
// behavior.
export function NavLink({ onNavigate, onClick, ...rest }: NavLinkProps): React.JSX.Element {
  return (
    <a
      {...rest}
      onClick={(event) => {
        onClick?.(event);
        if (isPlainLeftClick(event)) {
          event.preventDefault();
          onNavigate();
        }
      }}
    />
  );
}
