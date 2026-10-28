"use client";

/**
 * The image / video → ARM workflow, as one picture (public/acm/image-video-workflow.webp):
 *   1 scene input  ->  2 recognise objects and build the world (object library: geometry, mass,
 *   friction, restitution; environment: gravity, surfaces, collisions)  ->  3 define the action
 *   (text instruction or visual event)  ->  4 simulate consequences in a physics engine
 *   (e.g. Unreal Engine 5 / Chaos)  ->  5 render frames or video and explain them in the chat.
 * Used by the top-of-page intro, the image/video "How it works" sections and the physics lab.
 */

const ALT =
  "ARM image / video chat, from scene understanding to simulated consequences (proposed workflow). " +
  "1 Scene input: an image or video; extract a frame and establish the scene. " +
  "2 Recognise and build the world: computer vision identifies the objects (plant, mug, table); an object library gives geometry, mass, " +
  "friction and restitution; the environment adds gravity, surfaces and collisions; a 3D scene is reconstructed for simulation. " +
  "3 Define the action: a text instruction such as “push the mug to the right”, or a visual event; infer collision direction and motion. " +
  "4 Simulate consequences in a physics engine, e.g. Unreal Engine 5 / Chaos: apply forces and step through time — the mug slides, tips, falls. " +
  "5 Render and explain: output frames or video; the ARM chat explains the simulated outcome. " +
  "Property sources are measured, library or estimated; unknown values need assumptions or confirmation; " +
  "the simulation predicts outcomes under stated assumptions, not guaranteed real-world results.";

export function SceneFlow() {
  return (
    <figure className="flex flex-col gap-1">
      <a href="/acm/image-video-workflow.webp" target="_blank" rel="noreferrer" title="Open full size">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/acm/image-video-workflow.webp" alt={ALT} width={1880} height={660} className="block h-auto w-full rounded-md" />
      </a>
      <figcaption className="text-[11px] text-warn-400">
        Proposed workflow. In this prototype today: object recognition is mocked, properties come from the object library (typical values),
        matter.js in 2D stands in for Unreal Engine 5 / Chaos, and the output is a side-view replay rather than rendered frames.
      </figcaption>
    </figure>
  );
}
