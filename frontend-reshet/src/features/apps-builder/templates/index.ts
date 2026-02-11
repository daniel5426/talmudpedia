import type { PublishedAppTemplate } from "@/services";

export const sortTemplates = (templates: PublishedAppTemplate[]): PublishedAppTemplate[] => {
  return [...templates].sort((a, b) => a.name.localeCompare(b.name));
};
