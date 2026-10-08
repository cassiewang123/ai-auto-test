import type { ReactNode } from 'react';
import '../styles/tools-workspace.css';

export default function ToolPage({
  icon,
  title,
  description,
  extra,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="tools-workspace">
      <div className="tools-page-header">
        <div className="tools-page-heading">
          <span className="tools-page-icon">{icon}</span>
          <div>
            <h1 className="tools-page-title">{title}</h1>
            <div className="tools-page-description">{description}</div>
          </div>
        </div>
        {extra ? <div className="tools-page-extra">{extra}</div> : null}
      </div>
      {children}
    </div>
  );
}
