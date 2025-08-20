import chr from "chroma-js";
import { format } from "date-fns";
import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { IconCheck, IconEllipsis, IconMinus, IconSparks } from "@humansignal/icons";
import { Userpic, Button } from "@humansignal/ui";
import { Dropdown, Menu, Pagination } from "../../components";
import { Block, Elem } from "../../utils/bem";
import { absoluteURL } from "../../utils/helpers";
import { useCurrentUser } from "../../providers/CurrentUser";

const DEFAULT_CARD_COLORS = ["#FFFFFF", "#FDFDFC"];

export const ProjectsList = ({ projects, currentPage, totalItems, loadNextPage, pageSize }) => {
  const { user } = useCurrentUser();
  /*
   isOwner determines whether the current user has owner-level permissions for the
   active organization. Some backends do not expose user.isOwner, so we infer it:
   - Personal workspace (no active_organization_meta) => the current user is treated as the owner.
   - Otherwise, the owner is the account whose email matches active_organization_meta.email.

  */
  const isOwner = !user?.active_organization_meta || user?.email === user?.active_organization_meta?.email;
  // console.log('ProjectsList rendered', projects);

  // Single source of truth for project visibility logic
  const visibleProjects = useMemo(() => {
    return (projects ?? []).filter(project => {
      const participants = project.participants;
      if (isOwner) return true;
      if (!user?.lunor_username || !Array.isArray(participants)) return false;
      return participants.includes(user.lunor_username);
    });
  }, [projects, isOwner, user?.lunor_username]);

  if (!projects || projects.length === 0 || visibleProjects.length === 0) {
    return <EmptyProjectsList openModal={() => { }} isOwner={isOwner} />;
  }

  return (
    <>
      <Elem name="list">
        {visibleProjects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </Elem>
      <Elem name="pages">
        <Pagination
          name="projects-list"
          label="Projects"
          page={currentPage}
          totalItems={totalItems}
          urlParamName="page"
          pageSize={pageSize}
          pageSizeOptions={[10, 30, 50, 100]}
          onPageLoad={(page, pageSize) => loadNextPage(page, pageSize)}
        />
      </Elem>
    </>
  );
};

export const EmptyProjectsList = ({ openModal, isOwner = true }) => {
  return (
    <Block name="empty-projects-page">
      <Elem name="heidi" tag="img" src={absoluteURL("/static/images/opossum_looking.png")} onError={e => { e.target.style.display = 'none'; }} />
      <Elem name="header" tag="h1">
        No projects found!
      </Elem>
      <Block name="empty-projects-description">
        <p>
          {isOwner
            ? "You don't have any projects yet. Create a new project to start labeling your data."
            : "There are no projects available for you to view."}
        </p>
        {isOwner && (
          <Button onClick={openModal} className="my-8" aria-label="Create new project">
            Create Project
          </Button>
        )}
      </Block>
    </Block>
  );
};

const ProjectCard = ({ project }) => {
  const color = useMemo(() => {
    return DEFAULT_CARD_COLORS.includes(project.color) ? null : project.color;
  }, [project]);

  const projectColors = useMemo(() => {
    const textColor =
      color && chr(color).luminance() > 0.3
        ? "var(--color-neutral-inverted-content)"
        : "var(--color-neutral-inverted-content)"; // Determine text color based on luminance
    return color
      ? {
        "--header-color": color,
        "--background-color": chr(color).alpha(0.2).css(),
        "--text-color": textColor,
        "--border-color": chr(color).alpha(0.5).css(),
      }
      : {};
  }, [color]);

  return (
    // <Elem tag={NavLink} name="link" to={`/projects/${project.id}/data`} data-external>
    //   <Block name="project-card" mod={{ colored: !!color }} style={projectColors}>
    //     <Elem name="header">
    //       <Elem name="title">

    //         <Elem name="title-text">{project.title ?? "New project"}</Elem>
    //         {project.challenge_id && (
    //           <Elem name="challenge-id" style={{ fontSize: '0.85em', color: '#888', marginTop: 2 }}>
    //             Challenge ID: {project.challenge_id}
    //           </Elem>
    //         )}

    //         <Elem
    //           name="menu"
    //           onClick={(e) => {
    //             e.stopPropagation();
    //             e.preventDefault();
    //           }}
    //         >
    //           <Dropdown.Trigger
    //             content={
    //               <Menu contextual>
    //                 <Menu.Item href={`/projects/${project.id}/settings`}>Settings</Menu.Item>
    //                 <Menu.Item href={`/projects/${project.id}/data?labeling=1`}>Label</Menu.Item>
    //               </Menu>
    //             }
    //           >
    //             <Button size="smaller" look="string" aria-label="Project options">
    //               <IconEllipsis />
    //             </Button>
    //           </Dropdown.Trigger>
    //         </Elem>
    //       </Elem>
    //       <Elem name="summary">
    //         <Elem name="annotation">
    //           <Elem name="total">
    //             {project.finished_task_number} / {project.task_number}
    //           </Elem>
    //           <Elem name="detail">
    //             <Elem name="detail-item" mod={{ type: "completed" }}>
    //               <Elem tag={IconCheck} name="icon" />
    //               {project.total_annotations_number}
    //             </Elem>
    //             <Elem name="detail-item" mod={{ type: "rejected" }}>
    //               <Elem tag={IconMinus} name="icon" />
    //               {project.skipped_annotations_number}
    //             </Elem>
    //             <Elem name="detail-item" mod={{ type: "predictions" }}>
    //               <Elem tag={IconSparks} name="icon" />
    //               {project.total_predictions_number}
    //             </Elem>
    //           </Elem>
    //         </Elem>
    //       </Elem>
    //     </Elem>
    //     <Elem name="description">{project.description}</Elem>
    //     <Elem name="info">
    //       <Elem name="created-date">{format(new Date(project.created_at), "dd MMM ’yy, HH:mm")}</Elem>
    //       <Elem name="created-by">
    //         <Userpic src="#" user={project.created_by} showUsername />
    //       </Elem>
    //     </Elem>
    //   </Block>
    // </Elem>
    <Elem
      tag={NavLink}
      name="link"
      to={`/projects/${project.id}/data`}
      data-external
    >
      <Block
        name="project-card"
        mod={{ colored: !!color }}
        style={{
          ...projectColors,
          display: 'flex',
          flexDirection: 'column',
          padding: '16px',
          borderRadius: '12px',
          background: 'var(--color-bg-card)',
          boxShadow: 'var(--shadow-card)',
          transition: 'all 0.25s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-3px)';
          e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = 'var(--shadow-card)';
        }}
      >
        {/* Header */}
        <Elem
          name="header"
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
        >
          <div>
            <Elem name="title-text" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--color-text-primary)' }}>
              {project.title ?? "New project"}
            </Elem>
            {project.challenge_id && (
              <Elem name="challenge-id" style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                Challenge ID: {project.challenge_id} (round {project.round ? project.round : 1})
              </Elem>
            )}
          </div>

          <Elem
            name="menu"
            onClick={(e) => {
              e.stopPropagation();
              e.preventDefault();
            }}
          >
            <Dropdown.Trigger
              content={
                <Menu contextual>
                  <Menu.Item href={`/projects/${project.id}/settings`}>Settings</Menu.Item>
                  <Menu.Item href={`/projects/${project.id}/data?labeling=1`}>Label</Menu.Item>
                </Menu>
              }
            >
              <Button size="smaller" look="string" aria-label="Project options">
                <IconEllipsis />
              </Button>
            </Dropdown.Trigger>
          </Elem>
        </Elem>

        {/* Stats */}
        <Elem
          name="summary"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '12px',
            padding: '8px 12px',
            background: 'var(--color-bg-secondary)',
            borderRadius: '8px',
          }}
        >
          <Elem name="total" style={{ fontWeight: 500, color: 'var(--color-text-primary)' }}>
            {project.finished_task_number} / {project.task_number}
          </Elem>
          <Elem name="detail" style={{ display: 'flex', gap: '16px', fontSize: '0.85rem' }}>
            <Elem name="detail-item" mod={{ type: "completed" }} style={{ color: 'var(--color-success)' }}>
              <Elem tag={IconCheck} name="icon" /> {project.total_annotations_number}
            </Elem>
            <Elem name="detail-item" mod={{ type: "rejected" }} style={{ color: 'var(--color-danger)' }}>
              <Elem tag={IconMinus} name="icon" /> {project.skipped_annotations_number}
            </Elem>
            <Elem name="detail-item" mod={{ type: "predictions" }} style={{ color: 'var(--color-info)' }}>
              <Elem tag={IconSparks} name="icon" /> {project.total_predictions_number}
            </Elem>
          </Elem>
        </Elem>

        {/* Description */}
        {project.description && (
          <Elem
            name="description"
            style={{
              fontSize: '0.9rem',
              color: 'var(--color-text-secondary)',
              marginTop: '12px',
              lineHeight: 1.4,
            }}
          >
            {project.description}
          </Elem>
        )}

        {/* Footer */}
        <Elem
          name="info"
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 'auto',
            paddingTop: '12px',
            borderTop: '1px solid var(--color-border)',
            fontSize: '0.8rem',
            color: 'var(--color-text-secondary)',
          }}
        >
          <Elem name="created-date">
            {format(new Date(project.created_at), "dd MMM ’yy, HH:mm")}
          </Elem>
          <Elem name="created-by">
            <Userpic src="#" user={project.created_by} showUsername />
          </Elem>
        </Elem>
      </Block>
    </Elem>
  );
};
