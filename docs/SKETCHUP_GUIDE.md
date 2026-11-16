# CutList for SketchUp users

How to get a cutting plan from a SketchUp model: model it so CutList can read
it, check it, send it, and fix what the check finds.

Most interior designers draw in SketchUp. A model drawn to look good in a
render is usually not a model a workshop can cut from. This guide shows the few
habits that close that gap, and what to do when CutList tells you something is
wrong.

## Contents

1. [Two ways to get a model in](#1-two-ways-to-get-a-model-in)
2. [Model it so it can be cut](#2-model-it-so-it-can-be-cut)
3. [Worked example: a kitchen base unit](#3-worked-example-a-kitchen-base-unit)
4. [Install the extension and connect it](#4-install-the-extension-and-connect-it)
5. [Run the check](#5-run-the-check)
6. [Every message the check can show](#6-every-message-the-check-can-show)
7. [What happens after you send](#7-what-happens-after-you-send)
8. [Getting a model in by file instead](#8-getting-a-model-in-by-file-instead)
9. [Special cases](#9-special-cases)
10. [Troubleshooting](#10-troubleshooting)
11. [What CutList does not read from SketchUp](#11-what-cutlist-does-not-read-from-sketchup)
12. [One-page checklist](#12-one-page-checklist)

---

## 1. Two ways to get a model in

| | **Check and send** (extension) | **Export a file** (OBJ, DAE, STL) |
|---|---|---|
| What it reads | Each board's real length, width and thickness, straight from SketchUp | A triangle mesh of the whole model, which CutList turns back into boards |
| Rotated or scaled boards | Fine | Usually fine |
| Units | Always correct (read in SketchUp's own units and converted) | You must export in millimetres |
| Names | Your component names | Your group and component names, joined into long hierarchy names |
| Tells you what to fix | Yes, in a window inside SketchUp, before anything is sent | Only after upload, in the plan's notes |
| Status | **Server side tested. The SketchUp side has not been run in SketchUp yet.** | Works, tested on real exports, but less exact |

**Recommendation:** use the extension when it works for you, because it needs
no export and tells you what to fix. Use a file export when you cannot install
the extension or when the extension fails. Both give you the same plan screen.

> **Honest status.** The part of CutList that judges the parts, builds the
> check window and makes the project has automated tests. The Ruby code that
> runs inside SketchUp (measuring the model, opening the window, sending it) was
> written without SketchUp available and has **never been run**. Expect a rough
> edge on the first try. Try it on a small model first, and if the window says
> something unexpected or an error appears, note exactly what it said.

---

## 2. Model it so it can be cut

CutList does not guess your design intent. It finds boards. A **board** is a
group or component that is a flat piece of sheet material with a real thickness.
These ten habits make almost every model work.

### 2.1 One board, one component

Make every board its own **group or component** (right-click → *Make
Component*). Do not leave boards as loose faces or merge a whole carcass into a
single group, because CutList then sees one giant object, not its boards.

Components that are copies of each other (four identical shelves) are good.
Each copy counts as a separate board, and identical sizes are merged into one
line (`4 × Shelf`) in the parts list.

### 2.2 Give every board its real thickness

Draw boards as solids with their true thickness, for example 18 mm for a
carcass and 6 mm for a back. Use **Push/Pull** to give a flat face its
thickness. A single face with no thickness is a surface, not a board, and is
reported and left out.

### 2.3 Name your components

Select a component and type its name in **Entity Info** (*Window → Entity
Info*, then the *Instance* name box). Use the name you would write on the
shop floor:

`Left side`, `Right side`, `Top`, `Bottom`, `Back`, `Shelf`, `Shutter`,
`Drawer front`, `Partition`, `Skirting`.

- The name on the **instance** is used first. If it is empty, the **component
  definition** name is used.
- SketchUp's own defaults (`Component#3`, `Group#2`, `Group`) count as **no
  name**. Such boards are labelled by size, like `Unnamed 600 x 400`.
- Names appear on the cut sheet, the part labels and the parts list, so a good
  name saves you work later.

### 2.3.1 Use the same name for identical parts

Name copies the same way (`Shelf`). Do not number them by hand; CutList groups
them by name and size.

### 2.4 Keep hardware and decoration out, by name or by tag

Anything that is not sheet material should be named or tagged so CutList leaves
it out. A part is left out if its **name, component name or tag** contains any
of these words (whole words, any capitalisation, and `HingeCover` counts as
`Hinge Cover`):

> hinge, handle, knob, pull, screw, nail, dowel, channel, slide, runner, leg,
> foot, feet, castor, caster, hardware, fitting, bracket, light, lamp, bulb,
> led, socket, switch, plug, mirror, glass, tv, television, plant, decor,
> decoration, vase, person, people, human, figure, dimension, text, label, rod,
> hanger, accessory (and the plurals).

The easiest way is one **tag** called `Hardware` (or `Decor`, `Accessories`)
and put every handle, hinge, leg, mirror and plant on it. You do not need to
hide them.

A board whose name accidentally contains one of these words, such as a panel
called `Light box side`, will be left out. Rename it, and the check will list
it under *Parts left out* so you notice.

### 2.5 Hide what you do not want cut

Parts that are hidden, or on a **tag that is switched off**, are ignored. A
hidden parent hides everything inside it. Use this for construction aids,
alternatives and things already built.

### 2.6 Draw the board's true size, not the finished look

If a door is made of 18 mm board, draw it 18 mm thick at its real cut size.
A rendered door with a bevelled edge and a handle recess is fine, but the
**thickness must be the sheet's thickness** and the overall width and height the
real size.

### 2.7 Set the material name to the thickness, if you use materials

If you name materials, include the thickness in millimetres: `Plywood 18mm`,
`Hardboard 6mm`. CutList compares it with the drawn thickness and warns when
they disagree (for example a board drawn 16 mm but painted `Plywood 18mm`).
The **drawn** thickness is the one used.

### 2.8 Use standard board thicknesses

CutList knows these sheet thicknesses: **3, 4, 6, 8, 9, 12, 15, 16, 18, 19 and
25 mm**.

- A board within **0.5 mm** of one of these is read as that thickness. Drawn at
  17.9 mm, it is an 18 mm board.
- Anything further away is used as drawn, flagged *Not a common board
  thickness*, and given **sheets of its own**.
- Boards of different thicknesses are planned on separate sheets. A 6 mm back
  and 18 mm sides use two kinds of sheet.

### 2.9 Do not merge parts that are cut separately

Two boards that are one solid in SketchUp (a side and a shelf joined into one
group, or an L-shape drawn as one object) are measured as one part. Keep boards
separate, and let them touch.

### 2.10 Work in your normal units

With the extension, the model's units do not matter: it reads SketchUp's own
values. With a file export, see section 8.

---

## 3. Worked example: a kitchen base unit

A base unit 720 mm high, 600 mm wide and 560 mm deep, with 18 mm carcass and a
6 mm back.

| Component name | Tag | Drawn size (mm) | What CutList does |
|---|---|---|---|
| Left side | Carcass | 720 × 560 × 18 | Board |
| Right side | Carcass | 720 × 560 × 18 | Board (grouped with the left side) |
| Bottom | Carcass | 564 × 560 × 18 | Board |
| Top rail | Carcass | 564 × 100 × 18 | Board |
| Shelf | Carcass | 564 × 534 × 18 | Board |
| Back | Carcass | 684 × 564 × 6 | Board, on its own 6 mm sheet |
| Handle | Hardware | 128 × 12 × 12 | Left out: hardware |
| Leg | Hardware | 150 × 50 × 50 | Left out: hardware |

Result: 5 board sizes (6 pieces, because the two sides are the same size) on 2
sheets: one 18 mm and one 6 mm.

The size you see in SketchUp can be in any order: `720 × 560 × 18` and
`18 × 720 × 560` are the same board. CutList always reads it as **length ≥
width ≥ thickness**.

---

## 4. Install the extension and connect it

You need desktop SketchUp that allows Ruby extensions, and a CutList account.

1. **Get the file.** It is `sketchup_plugin/cutlist_engine_loader.rb` in the
   CutList repository.
2. **Copy it into SketchUp's Plugins folder.**
   - Windows: `%AppData%\SketchUp\SketchUp <year>\SketchUp\Plugins\`
   - macOS: `~/Library/Application Support/SketchUp <year>/SketchUp/Plugins/`
3. **Restart SketchUp.** A menu appears: **Extensions → Cutlist Engine**.
4. **Create an API key.** In the CutList web app, open **API keys → Create API
   key** and copy the key. It is shown **once**. Keep it private.
5. **Connect.** In SketchUp choose **Extensions → Cutlist Engine → CutList
   connection…** and fill in:
   - *Server address*: where your CutList runs, for example
     `https://cutlist.example.com`, or `http://localhost:8000` if you run it on
     your own computer.
   - *API key*: the key you copied.

The address and key are stored in SketchUp's preferences on **this computer**.
To disconnect, revoke the key in the web app under **API keys → Revoke**.

The menu items:

| Item | What it does |
|---|---|
| **Check and send to CutList** | Reads your boards, shows the check window, sends on request. Recommended. |
| Send to CutList (as a mesh) | Older path: uploads an OBJ of the model. No check window. |
| CutList connection… | Sets the server address and API key. |
| Export selection to OBJ for cutlist | Saves an OBJ next to your file. Nothing is sent. |
| Export and run cutlist-engine | Runs the command-line tool on this computer. |

---

## 5. Run the check

1. **Choose what to read.** Select the furniture you want planned, or select
   nothing to read the **whole model**. Reading a selection is best when a
   model holds a whole room, because it avoids wardrobes, props and people.
2. Choose **Extensions → Cutlist Engine → Check and send to CutList**.
3. A window opens. From top to bottom it shows:
   - **A headline.** Either "*N boards found*" with a count per thickness, or
     "*Not ready to send*".
   - **Notes**, most serious first, each with a short explanation and what to
     do (see section 6). The names of the parts concerned are listed.
   - **Boards**: the parts as they will be cut, one line per distinct board
     (`4 × Shelf 564 × 534 × 18`).
   - **Left out of the plan**: every part that was not treated as a board, and
     why.
4. **Decide.**
   - If something needs fixing, close the window, fix the model, and run the
     check again. It is quick and changes nothing on the server.
   - If it looks right, press **Send to CutList**. The button is greyed out
     when no boards were found.
5. Your browser opens on CutList while the plan is made. A small model takes
   seconds.

Nothing is created on the server until you press **Send**. Running the check as
often as you like costs nothing and leaves nothing behind.

How it reads the model, in detail:

- **A "part" is any group or component that has faces of its own.** A cabinet
  group made only of other components is not a part; its components are.
- **Nested parts are read separately.** A handle inside a door does not change
  the door's size, because the door's size comes from the door's **own faces**.
- **The size is the part's box in its own axes**, multiplied by any scaling
  above it, and converted from inches to millimetres. A board rotated to any
  angle still reads as length, width, thickness.
- **Up to 5,000 parts** can be checked at once. Select just the furniture if a
  model is larger.

---

## 6. Every message the check can show

Messages come in three kinds:

- **Fix first** (stops sending): nothing can be cut until it is fixed.
- **Check** (warning): the plan can be made, but you should look at it.
- **Good to know**: information only.

| Message | Kind | What it means | What to do |
|---|---|---|---|
| **No boards found** | Fix first | None of the parts looked like a board, so there is nothing to plan. | Select the furniture, make each board its own group or component, and give it real thickness. Check that boards are not all on a hidden tag. |
| **Flat surfaces without thickness** | Check | These parts are a single face (under 2 mm thick), so there is no board to measure. They are left out. | Give each one thickness with **Push/Pull**, then check again. |
| **Material does not match the drawn thickness** | Check | The material name says one thickness (for example `Ply 12mm`) but the board is drawn another (18 mm). The **drawn** thickness is used. | Correct whichever is wrong: the board or the material name. |
| **Not a common board thickness** | Check | Drawn thickness is not within 0.5 mm of 3, 4, 6, 8, 9, 12, 15, 16, 18, 19 or 25 mm. It is used as drawn and put on its own sheets. | Redraw at a standard thickness, or accept it if you really buy that board. |
| **Shaped or curved boards** | Check | The board fills under 60% of its bounding rectangle (an arch, a big curve, a large cut-out). It is planned as its **full rectangle**, so it wastes sheet. | Cut it from a drawing of the real shape on a CNC, or accept the rectangle. |
| **Boards without a name** | Check | The part has no useful name (empty, or SketchUp's `Component#3`). It is labelled by size, such as `Unnamed 600 x 400`. | Name the component in Entity Info. |
| **Boards with notches or holes** | Good to know | The board fills 60–97% of its rectangle, for example hinge cups, a notch for a pipe, or dowel holes. It is planned as a full rectangle, and the holes and notches are cut afterwards. | Nothing, unless the notch is large. |
| **Parts left out of the plan** | Good to know | Some parts were not treated as boards. The reasons are listed below. | If one is a real board, fix its thickness or size (see the reasons table below). |
| **Hidden parts ignored** | Good to know | Parts that are hidden, or on a hidden tag, were not sent. | Show them first if they should be cut. |

### Reasons a part is left out

| Reason shown | When | What to do if it is a real board |
|---|---|---|
| *hardware or decoration ("handle")* | Its name, component name or tag contains a word from the hardware list in section 2.4. | Rename the board, or take it off the Hardware/Decor tag. |
| *a flat surface with no thickness (0.4 mm)* | Thinner than **2 mm**. | Push/Pull it to its thickness. |
| *a block 90 mm thick, not sheet material* | Thicker than **60 mm**: a post, solid timber or a block. | Boards are sheet material; solid timber is cut with the cut-lengths tool, not the sheet plan. |
| *smaller than 50 mm across (trim, edge strip or hardware)* | The board's **width is under 50 mm**. | A real narrow strip (a 40 mm rail) is below the plan's minimum part size. Group strips into a wider board if they are cut from the same sheet, or cut them from solid timber. |
| *no size* | A dimension is zero or missing. | Redraw the part. |

### The cut-lengths tool

Solid timber, beading and pipe are not cut from sheets. Use **Cut lengths** in
the CutList web app for those; it plans pieces on stock bars.

---

## 7. What happens after you send

A new project appears in your CutList projects with the model's title as its
name. The plan is made from your boards with these **defaults**:

- sheet size **2440 × 1220 mm** (8 × 4 ft)
- blade thickness (kerf) **3 mm**
- sheet price **₹3,500**
- main board thickness = the thickness that covers the **most area** in your
  model

Parts of other thicknesses are planned on their own sheets, priced like the
main sheet.

> The extension sends no sheet size or price. If your sheets are not 2440 ×
> 1220 mm or cost something else, the plan's sheet count will be right for the
> default sheet but its cost will not be. To plan on a different sheet,
> upload an exported file in the web app, where you choose the sheet size and
> price. Setting these from SketchUp is not built yet.

On the plan screen you can then:

- read each **sheet** (see below), and tap a part in the list to find it;
- add **edge banding** to parts and see the metres of tape;
- build a **quote** for your customer and share a link that shows only the
  total;
- **print** the plan, download **part labels**, a **CSV** for Excel, and the
  **DXF and G-code** files for a CNC machine;
- ask the **AI assistant** (when switched on) to propose changes such as tape,
  names or quote amounts, which you approve before they are applied.

Reading a sheet:

- The sheet looks like plywood, with its size shown along two edges.
- Each cut piece is tinted by kind of part and carries a **number** that matches
  the `#` column in the parts list.
- Hover or tap a part for its size, thickness and tape. Selecting a part dims
  the others.
- Green hatched areas are **spare pieces worth keeping**. Save them to your
  offcut shelf to cut from them next time.

---

## 8. Getting a model in by file instead

Use this when the extension is unavailable.

### 8.1 Prepare the model

Follow section 2. For a file export the habits matter more, because CutList has
to rebuild boards from triangles.

### 8.2 Export

1. **File → Export → 3D Model…**
2. Choose **OBJ** (recommended), or **DAE**.
3. In the export options, set the units to **millimetres** if the option is
   offered. Which options and formats appear depends on your SketchUp edition
   and version.
4. Export just the furniture: select it first and choose the *selection only*
   option if there is one.

### 8.3 Upload

In the CutList web app: **New project → I have a 3D file**, choose the file,
set sheet size, board thickness and sheet price, then continue.

### 8.4 Units: the most common cause of wrong sizes

- **OBJ and STL have no unit information.** CutList reads them as
  **millimetres**. Export in millimetres.
- If a whole model is **under 20 units across**, CutList assumes you exported
  in **metres** and scales it by 1000, and says so in the plan's notes. This
  catches a Blender-style export. It does not catch **inches or centimetres**.
- **DAE files declare their unit** (SketchUp writes inches). CutList reads it
  and converts to millimetres, and says so in the plan's notes
  ("This file declares its unit as 'inch'…"). If a DAE has no unit, the
  under-20-units metres guess above applies. If a declared unit would make the
  model over 100 m across, the declaration is ignored as wrong.
- After any upload, compare one known size (the cabinet height) with the plan.
  If it is wrong, the units are wrong.

### 8.5 What is different from the extension

- Names are joined from the whole hierarchy (`Mesh9 Component30_1 Group4 …`).
  CutList keeps the board's own component name and drops the generic parts.
- A board that is not a **closed solid** is rebuilt from loose faces and is
  marked as less reliable. The plan lists these under *Good to know*.
- Curved or decorative geometry is reported as "not flat panels" and left out.
- There is no check window before you upload; read the plan's notes instead.

---

## 9. Special cases

### Doors, shutters and drawer fronts

Draw each at its **real cut size**. If shutters overlay the carcass with 3 mm
gaps, draw them with those gaps. Name them `Shutter`, `Drawer front`. They are
the parts that usually get edge banding on all edges, which you set on the plan
screen.

### Drawers

Draw every board of the drawer box as its own component: front, back, two
sides, base. Name the slides and channels with the word `Slide` or `Channel`
(or put them on the Hardware tag) so they are left out.

### Backs

Draw the back at its real thickness, for example 6 mm. It is planned on its
own 6 mm sheet, which is correct if you buy hardboard or thin ply separately.

### Edge banding

Edge banding is **not read from SketchUp**. Add it on the plan screen (*Edge
banding* card) after sending. Taped parts are cut smaller by the tape thickness
so they finish at the drawn size. Because the plan then changes, re-check
critical sizes.

### Grain

SketchUp's material or texture direction is **not read**. Set grain locks in
the plan's overrides if a board's grain matters.

### Curved, arched or shaped boards

The board is planned as the full rectangle it fits in (its bounding box), so
the plan is **safe but wasteful**. A CNC job from the true outline needs a
separate drawing. The check lists such boards under *Shaped or curved boards*.

### Boards with a groove or rebate

A shallow groove removes little of the board's face, so it is usually read as a
plain board (97% or more of its rectangle). The groove itself is not in the
plan.

### Scaled components

A component stretched with the Scale tool is fine: CutList multiplies the
stretch into the size. A **mirrored** (flipped) component should read the same,
but this has not been tried in SketchUp, so check one.

### Dynamic Components

They are read as their current geometry. Their attributes (such as a
`LenX` value) are **not** read.

### Large models

Select only the furniture. A whole-house model can contain thousands of parts.
The limit is 5,000 parts per check.

---

## 10. Troubleshooting

### In SketchUp

| What you see | Likely cause | What to do |
|---|---|---|
| The **Cutlist Engine** menu is missing | The file is not in the Plugins folder, or SketchUp was not restarted, or the Ruby file has an error | Check the folder, restart, then open the **Ruby Console** (*Window → Ruby Console*) and look for an error to report |
| "*No groups or components were found*" | Everything is loose geometry, or the selection holds no groups | Make each board a component, or select the furniture |
| "*Could not reach … (SocketError…)*" | The server address is wrong, the server is down, or there is no internet | Check the address under *CutList connection…*; open it in a browser |
| "*The API key was not accepted*" | The key was mistyped, revoked, or belongs to another server | Create a new key in the web app and enter it again |
| "*Could not check the model*" plus a message | The server rejected the request, or the server is older than the extension | Read the message; make sure the server has been updated to the same version as the extension |
| The check window opens blank | The window did not receive the page | Close and run the check again; report it |
| *Send to CutList* does nothing or shows an error | Not known: this part of the extension has not been run | Close and run the check again; use *Send to CutList (as a mesh)* meanwhile, and note any error in the Ruby Console |

### In the check window

| What you see | Likely cause | What to do |
|---|---|---|
| A board you expected is under *Left out* | Its name has a hardware word, it is thinner than 2 mm, thicker than 60 mm, or narrower than 50 mm | Read the reason, then change the name, thickness or tag |
| A board is missing everywhere | It, its parent or its tag is hidden | Show it, then check again |
| Every board is `Unnamed …` | Components are not named | Name them in Entity Info |
| Two boards of the same name have different sizes | They really are different sizes | Check the drawing, or name them differently |
| Thickness is 17.9 but the plan says 18 | Within 0.5 mm of a standard board | Expected |
| Sizes look 1 mm off | The model was drawn 1 mm short, or a board is slightly rotated off-axis | Redraw to exact sizes; a small skew in the board changes its box |

### On the plan screen

| What you see | Likely cause | What to do |
|---|---|---|
| "*N part(s) are bigger than the sheet and are NOT in the plan*" | A board is longer than the sheet (for example a 3 m top on a 2.44 m sheet) | Split the board in the design, or use a longer sheet |
| More sheets than you expected | Several thicknesses, a very wide board, or few boards per sheet | Look at the sheets; a 6 mm back and 18 mm carcass use at least two sheets |
| A sheet is almost empty | A single large part or its thickness has few boards | Check whether those boards can be a different thickness, or use offcuts |
| Costs look wrong | Defaults were used | See section 7: the extension sends the default sheet price |

---

## 11. What CutList does not read from SketchUp

Be aware of these so there are no surprises:

- **Grain direction, textures and colours.** Not read.
- **Edge banding.** Not read. Set it on the plan screen.
- **Hardware lists.** Hardware is left out, not counted. Hinge and channel
  counts are suggested only for described furniture.
- **Joinery** (dados, rebates, pockets, dowel holes). Not in the plan.
- **True curved outlines.** Boards are planned as their bounding rectangle.
- **Dynamic Component attributes.**
- **Scenes, styles and section cuts.**
- **Sheet size and price.** Defaults are used when sending from the extension.
- **Anything inside a group that is also exported by another name.** If the
  same board is modelled twice (once for the render, once for the cut), both
  are counted. Hide or tag the one you do not want.

---

## 12. One-page checklist

Before you check:

- [ ] Every board is its own group or component.
- [ ] Every board has its **real thickness** (Push/Pull), at 3, 4, 6, 8, 9, 12,
      15, 16, 18, 19 or 25 mm.
- [ ] Every board is **named** in Entity Info: *Left side*, *Shelf*, *Back*…
- [ ] Identical parts have the **same name**.
- [ ] Handles, hinges, legs, mirrors and decor are on a **Hardware / Decor**
      tag.
- [ ] Anything not to be cut is **hidden** or on a hidden tag.
- [ ] No board is merged with another.
- [ ] Boards are drawn at **cut size**, with real gaps.
- [ ] Material names, if used, include the thickness (`Plywood 18mm`).
- [ ] Only the furniture is **selected**.

Then:

- [ ] Run **Check and send to CutList**.
- [ ] Fix every **Fix first** item.
- [ ] Read every **Check** item.
- [ ] Look at *Left out of the plan*.
- [ ] Send.
- [ ] Compare one known size and the sheet count with your expectation.
- [ ] Add edge banding and the quote on the plan screen.

If you export a file instead: millimetres, OBJ, selection only, and check one
known size after uploading.
