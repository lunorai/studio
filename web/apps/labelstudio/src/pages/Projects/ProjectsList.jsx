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
  const isOwner = !user?.active_organization_meta || user?.email === user?.active_organization_meta?.email;


  // Single source of truth for project visibility logic
  const canViewProject = isOwner;
  const visibleProjects = canViewProject ? projects : [];

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

export const EmptyProjectsList = ({ openModal, isOwner=true }) => {
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
    <Elem tag={NavLink} name="link" to={`/projects/${project.id}/data`} data-external>
      <Block name="project-card" mod={{ colored: !!color }} style={projectColors}>
        <Elem name="header">
          <Elem name="title">
            <Elem name="title-text">{project.title ?? "New project"}</Elem>

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
          <Elem name="summary">
            <Elem name="annotation">
              <Elem name="total">
                {project.finished_task_number} / {project.task_number}
              </Elem>
              <Elem name="detail">
                <Elem name="detail-item" mod={{ type: "completed" }}>
                  <Elem tag={IconCheck} name="icon" />
                  {project.total_annotations_number}
                </Elem>
                <Elem name="detail-item" mod={{ type: "rejected" }}>
                  <Elem tag={IconMinus} name="icon" />
                  {project.skipped_annotations_number}
                </Elem>
                <Elem name="detail-item" mod={{ type: "predictions" }}>
                  <Elem tag={IconSparks} name="icon" />
                  {project.total_predictions_number}
                </Elem>
              </Elem>
            </Elem>
          </Elem>
        </Elem>
        <Elem name="description">{project.description}</Elem>
        <Elem name="info">
          <Elem name="created-date">{format(new Date(project.created_at), "dd MMM ’yy, HH:mm")}</Elem>
          <Elem name="created-by">
            <Userpic src="#" user={project.created_by} showUsername />
          </Elem>
        </Elem>
      </Block>
    </Elem>
  );
};
