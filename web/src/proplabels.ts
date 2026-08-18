/** Display labels for date properties and the nested-date parent properties
 * (the app-level complement of cg_rels, which the server already labels). */

export const DATE_PROP_LABELS: Record<string, string> = {
  // starts
  P569: 'date of birth',
  P571: 'inception',
  P580: 'start time',
  P577: 'publication date',
  P575: 'time of discovery or invention',
  P1191: 'first performance',
  P729: 'service entry',
  P2031: 'work period start',
  P3999: 'date of official closing',
  P1619: 'date of official opening',
  P6949: 'announcement date',
  P1319: 'earliest date',
  // ends
  P570: 'date of death',
  P582: 'end time',
  P576: 'dissolved or demolished',
  P730: 'service retirement',
  P746: 'date of disappearance',
  P2032: 'work period end',
  P2669: 'discontinued date',
  P1326: 'latest date',
  // others
  P585: 'point in time',
  P1317: 'floruit',
  P813: 'retrieved',
  P1249: 'earliest written record',
  // nested-date parent claims
  P108: 'employer',
  P106: 'occupation',
  P69: 'educated at',
  P26: 'spouse',
  P449: 'original broadcaster',
  P793: 'significant event',
  P348: 'software version',
  P1891: 'signatory',
};

export function propLabel(prop: string,
                          extra?: Record<string, string> | null): string {
  const label = DATE_PROP_LABELS[prop] ?? extra?.[prop];
  return label ? `${prop} ${label}` : prop;
}
