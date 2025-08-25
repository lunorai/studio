import { useMemo } from "react";
import { Menu } from "../Menu/Menu";
import { useCurrentUserAtom } from "libs/core/src/lib/hooks/useCurrentUser";

export const TabsMenu = ({ onClick, editable = true, closable = true, clonable = true, virtual = false }) => {
  const { user } = useCurrentUserAtom();
  const isOwner = Boolean(user?.isOwner) || (
    Boolean(user?.active_organization_meta?.email) && user?.email === user?.active_organization_meta?.email
  );
  const items = useMemo(
    () => [
      {
        key: "edit",
        title: "Rename",
        enabled: isOwner && editable && !virtual,
        action: () => onClick("edit"),
      },
      {
        key: "duplicate",
        title: "Duplicate",
        enabled: isOwner && !virtual && clonable,
        action: () => onClick("duplicate"),
        willLeave: true,
      },
      {
        key: "save",
        title: "Save",
        enabled: virtual,
        action: () => onClick("save"),
        willLeave: true,
      },
    ],
    [editable, closable, clonable, virtual, isOwner],
  );

  const showDivider = useMemo(() => closable && items.some(({ enabled }) => enabled), [items]);

  return (
    <Menu size="medium" onClick={(e) => e.domEvent.stopPropagation()}>
      {items.map((item) =>
        item.enabled ? (
          <Menu.Item key={item.key} onClick={item.action} data-leave={item.willLeave}>
            {item.title}
          </Menu.Item>
        ) : null,
      )}

      {closable ? (
        <>
          {showDivider && <Menu.Divider />}
          <Menu.Item onClick={() => onClick("close")} data-leave>
            Close
          </Menu.Item>
        </>
      ) : null}
    </Menu>
  );
};
