"use client";

import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface SearchableResourceOption {
  value: string;
  label: string;
  info?: string;
}

interface SearchableResourceInputProps {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  className?: string;
  resources: SearchableResourceOption[];
}

export function SearchableResourceInput({
  value,
  onChange,
  placeholder,
  className,
  resources = [],
}: SearchableResourceInputProps) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedResource = resources.find((resource) => resource.value === value);
  const [query, setQuery] = useState(selectedResource?.label || "");
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => {
    if (!isFocused) {
      setQuery(selectedResource?.label || value || "");
    }
  }, [value, selectedResource, isFocused]);

  const filteredResources = resources.filter((resource) =>
    resource.label.toLowerCase().includes(query.toLowerCase()) ||
    resource.value.toLowerCase().includes(query.toLowerCase())
  );

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (!showSuggestions || filteredResources.length === 0) {
      event.stopPropagation();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      setSelectedIndex((index) => (index + 1) % filteredResources.length);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      setSelectedIndex((index) => (index - 1 + filteredResources.length) % filteredResources.length);
      return;
    }

    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      event.stopPropagation();
      const selected = filteredResources[selectedIndex];
      onChange(selected.value);
      setQuery(selected.label);
      setShowSuggestions(false);
      return;
    }

    if (event.key === "Escape") {
      event.stopPropagation();
      setShowSuggestions(false);
      return;
    }

    event.stopPropagation();
  };

  return (
    <div className="relative">
      <div className="relative">
        <Input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setShowSuggestions(true);
          }}
          onFocus={() => {
            setIsFocused(true);
            setShowSuggestions(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className={cn(className, "pr-8")}
          onBlur={() => {
            setIsFocused(false);
            setShowSuggestions(false);
          }}
        />
        {query ? (
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/40 hover:text-muted-foreground"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setQuery("");
              onChange("");
            }}
          >
            <X className="h-3 w-3" />
          </button>
        ) : null}
      </div>
      {showSuggestions && filteredResources.length > 0 ? (
        <div className="absolute z-50 w-full mt-1 bg-popover text-popover-foreground shadow-md rounded-md border border-border p-1 max-h-[200px] overflow-auto">
          {filteredResources.map((resource, index) => (
            <div
              key={resource.value}
              className={cn(
                "flex flex-col px-2 py-1.5 text-xs rounded-sm cursor-pointer",
                index === selectedIndex ? "bg-accent text-accent-foreground" : "hover:bg-muted"
              )}
              onMouseDown={(event) => {
                event.preventDefault();
                onChange(resource.value);
                setQuery(resource.label);
                setShowSuggestions(false);
              }}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{resource.label}</span>
                {resource.value === value ? <Check className="h-3 w-3 text-primary" /> : null}
              </div>
              <span className="text-[10px] opacity-50 font-mono truncate">{resource.info || resource.value}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
