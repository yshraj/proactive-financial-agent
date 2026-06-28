import React from "react";

export function Card({
  className = "",
  children,
  as: As = "div",
  ...rest
}: {
  className?: string;
  children: React.ReactNode;
  as?: React.ElementType;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <As
      className={`rounded-xl border border-gray-200 bg-white shadow-card ${className}`}
      {...rest}
    >
      {children}
    </As>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-6 py-5">
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-gray-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export default Card;
