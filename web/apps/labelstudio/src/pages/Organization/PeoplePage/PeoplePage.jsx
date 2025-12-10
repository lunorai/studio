import { Button } from "@humansignal/ui";
import { useCallback, useMemo, useRef, useState } from "react";
import { HeidiTips } from "../../../components/HeidiTips/HeidiTips";
import { modal } from "../../../components/Modal/Modal";
import { Space } from "../../../components/Space/Space";
import { Block, Elem } from "../../../utils/bem";
import { FF_AUTH_TOKENS, FF_LSDV_E_297, isFF } from "../../../utils/feature-flags";
import "./PeopleInvitation.scss";
import { PeopleList } from "./PeopleList";
import "./PeoplePage.scss";
import { TokenSettingsModal } from "@humansignal/app-common/blocks/TokenSettingsModal";
import { IconPlus } from "@humansignal/icons";
import { useToast } from "@humansignal/ui";
import { InviteLink } from "./InviteLink";
import { SelectedUser } from "./SelectedUser";
import { useCurrentUser } from "../../../providers/CurrentUser";

export const PeoplePage = () => {
  const apiSettingsModal = useRef();
  const toast = useToast();
  const [selectedUser, setSelectedUser] = useState(null);
  const [invitationOpen, setInvitationOpen] = useState(false);
  const { user } = useCurrentUser();
  /*
   isOwner determines whether the current user has owner-level permissions for the
   active organization. Some backends do not expose user.isOwner, so we infer it:
   - Personal workspace (no active_organization_meta) => the current user is treated as the owner.
   - Otherwise, the owner is the account whose email matches active_organization_meta.email.
  */

  // const isOwner = !user?.active_organization_meta || user?.email === user?.active_organization_meta?.email;
  const isOwner = !!user && (!user?.active_organization_meta || user?.email === user?.active_organization_meta?.email);
 

  const selectUser = useCallback(
    (user) => {
      setSelectedUser(user);

      localStorage.setItem("selectedUser", user?.id);
    },
    [setSelectedUser],
  );

  const apiTokensSettingsModalProps = useMemo(
    () => ({
      title: "API Token Settings",
      style: { width: 480 },
      body: () => (
        <TokenSettingsModal
          onSaved={() => {
            toast.show({ message: "API Token settings saved" });
            apiSettingsModal.current?.close();
          }}
        />
      ),
    }),
    [],
  );

  const showApiTokenSettingsModal = useCallback(() => {
    apiSettingsModal.current = modal(apiTokensSettingsModalProps);
    __lsa("organization.token_settings");
  }, [apiTokensSettingsModalProps]);

  const defaultSelected = useMemo(() => {
    return localStorage.getItem("selectedUser");
  }, []);

  return (
    <Block name="people">
      <Elem name="controls">
        <Space spread>
          <Space />

          {/* <Space>

            {isOwner && (isFF(FF_AUTH_TOKENS) && (
              <Button look="outlined" onClick={showApiTokenSettingsModal} aria-label="Show API token settings" 
              className="hover:!bg-transparent !border-[#EABE00] !text-[#EABE00]"
              >
                API Tokens Settings
              </Button>
            ))}
            {
              isOwner && (
                <Button
                  leading={<IconPlus className="!h-4" />}
                  onClick={() => setInvitationOpen(true)}
                  aria-label="Invite new member"
                  className="!bg-[#EABE00] !border-[#EABE00]"
                >
                  Add People
                </Button>
              )}
          </Space> */}
        </Space>
      </Elem>
      <Elem name="content">
        <PeopleList
          selectedUser={selectedUser}
          defaultSelected={defaultSelected}
          onSelect={(user) => selectUser(user)}
        />

        {selectedUser ? (
          <SelectedUser user={selectedUser} onClose={() => selectUser(null)} />
        ) : (
          isFF(FF_LSDV_E_297) && /* <HeidiTips collection="organizationPage" /> */ null
        )}
      </Elem>
      <InviteLink
        opened={invitationOpen}
        onClosed={() => {
          console.log("hidden");
          setInvitationOpen(false);
        }}
      />
    </Block>
  );
};

PeoplePage.title = "People";
PeoplePage.path = "/";
