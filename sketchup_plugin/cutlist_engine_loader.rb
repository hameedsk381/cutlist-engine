# Cutlist Engine - SketchUp plugin loader
# ----------------------------------------
# Drop this file into your SketchUp Plugins folder, e.g.:
#   Windows: %AppData%/SketchUp/SketchUp 2024/SketchUp/Plugins/
#   macOS:   ~/Library/Application Support/SketchUp 2024/SketchUp/Plugins/
#
# It adds a "Cutlist Engine" menu under Extensions with two actions:
#   1. Export selection (or model) to OBJ
#   2. Export and run cutlist-engine CLI on it
#
# The plugin does NOT call any external service. It writes a local OBJ next to
# the .skp file and either stops there or shells out to the cutlist-engine CLI
# you installed via `pip install -e .`.

require 'sketchup.rb'
require 'extensions.rb'

module CutlistEngine
  PLUGIN_NAME    = 'Cutlist Engine'.freeze
  PLUGIN_VERSION = '1.0.0'.freeze

  module_function

  # ---------------------------------------------------------------------------
  # OBJ export
  # ---------------------------------------------------------------------------

  def export_to_obj(path)
    model = Sketchup.active_model
    entities = model.selection.empty? ? model.entities : model.selection

    triangles = []
    object_stack = []
    collect_triangles(entities, Geom::Transformation.new, object_stack, triangles)

    File.open(path, 'w') do |f|
      f.puts "# CutlistEngine SketchUp export v#{PLUGIN_VERSION}"
      f.puts "# Units: millimetres (auto-converted from SketchUp inches)"

      vertex_index = 1
      current_object = nil
      triangles.each do |tri|
        if tri[:object_name] != current_object
          current_object = tri[:object_name]
          f.puts "o #{current_object || 'panel'}"
        end
        tri[:vertices].each do |v|
          # SketchUp internal units are inches; convert to mm.
          mm = v.to_a.map { |c| (c * 25.4).round(4) }
          f.puts "v #{mm[0]} #{mm[1]} #{mm[2]}"
        end
        f.puts "f #{vertex_index} #{vertex_index + 1} #{vertex_index + 2}"
        vertex_index += 3
      end
    end
    path
  end

  def collect_triangles(entities, transform, object_stack, sink)
    entities.each do |entity|
      case entity
      when Sketchup::Group, Sketchup::ComponentInstance
        new_transform = transform * entity.transformation
        new_stack = object_stack + [entity_name(entity)]
        children = entity.is_a?(Sketchup::Group) ? entity.entities : entity.definition.entities
        collect_triangles(children, new_transform, new_stack, sink)
      when Sketchup::Face
        # Triangulate the face's polygon mesh in world space.
        mesh = entity.mesh(0)
        next unless mesh
        mesh.polygons.each do |poly|
          # `poly` is an array of 1-based vertex indices into `mesh.points`.
          next if poly.length != 3
          verts = poly.map { |i| mesh.point_at(i.abs).transform(transform) }
          sink << { vertices: verts, object_name: object_stack.last }
        end
      end
    end
  end

  def entity_name(entity)
    name = entity.respond_to?(:name) ? entity.name : ''
    return name unless name.nil? || name.empty?
    if entity.is_a?(Sketchup::ComponentInstance)
      entity.definition.name
    else
      entity.entityID.to_s
    end
  end

  # ---------------------------------------------------------------------------
  # CLI wrapper
  # ---------------------------------------------------------------------------

  def run_cli(obj_path, output_dir)
    cmd = "cutlist-engine \"#{obj_path}\" --output-dir \"#{output_dir}\""
    UI.messagebox("Running:\n#{cmd}\n\nOpen a terminal in the output folder to see the report.html.")
    if Sketchup.platform == :platform_win
      system("cmd /c start \"\" \"#{output_dir}\"")
    else
      system("open \"#{output_dir}\"")
    end
    cmd
  end

  # ---------------------------------------------------------------------------
  # UI wiring
  # ---------------------------------------------------------------------------

  def menu_action_export
    model = Sketchup.active_model
    base = model.path.empty? ? File.join(Dir.home, 'Desktop', 'sketchup_export') : model.path.sub(/\.skp$/i, '')
    obj_path = "#{base}_cutlist.obj"
    export_to_obj(obj_path)
    UI.messagebox("Exported #{obj_path}\n\nNow run:\n  cutlist-engine \"#{obj_path}\" --output-dir out")
  end

  def menu_action_export_and_run
    model = Sketchup.active_model
    base = model.path.empty? ? File.join(Dir.home, 'Desktop', 'sketchup_export') : model.path.sub(/\.skp$/i, '')
    obj_path = "#{base}_cutlist.obj"
    output_dir = "#{base}_cutlist_out"
    export_to_obj(obj_path)
    Dir.mkdir(output_dir) unless Dir.exist?(output_dir)
    run_cli(obj_path, output_dir)
  end

  unless file_loaded?(__FILE__)
    menu = UI.menu('Extensions').add_submenu(PLUGIN_NAME)
    menu.add_item('Export selection to OBJ for cutlist') { menu_action_export }
    menu.add_item('Export and run cutlist-engine')        { menu_action_export_and_run }
    file_loaded(__FILE__)
  end
end
