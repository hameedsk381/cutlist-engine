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
require 'net/http'
require 'uri'
require 'json'
require 'tmpdir'

module CutlistEngine
  PLUGIN_NAME    = 'Cutlist Engine'.freeze
  PLUGIN_VERSION = '1.1.0'.freeze
  PREFS          = 'CutlistEngine'.freeze

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
  # Send to a CutList server (hosted or self-hosted) with an API key
  # ---------------------------------------------------------------------------

  def server_url
    Sketchup.read_default(PREFS, 'server_url', '').to_s.sub(%r{/+\z}, '')
  end

  def api_key
    Sketchup.read_default(PREFS, 'api_key', '').to_s
  end

  # Ask for the server address and API key. Returns true when both are set.
  def menu_action_settings
    answers = UI.inputbox(
      ['Server address', 'API key'],
      [server_url.empty? ? 'http://localhost:8000' : server_url, api_key],
      'CutList connection'
    )
    return false unless answers
    Sketchup.write_default(PREFS, 'server_url', answers[0].to_s.strip.sub(%r{/+\z}, ''))
    Sketchup.write_default(PREFS, 'api_key', answers[1].to_s.strip)
    !server_url.empty? && !api_key.empty?
  end

  # POST the OBJ as a new project. Returns [ok, message_or_project_hash].
  def upload_project(obj_path, name, server, key)
    uri = URI.parse("#{server}/api/projects")
    request = Net::HTTP::Post.new(uri)
    request['Authorization'] = "Bearer #{key}"
    File.open(obj_path, 'rb') do |file|
      request.set_form(
        [['name', name], ['file', file, { filename: File.basename(obj_path), content_type: 'text/plain' }]],
        'multipart/form-data'
      )
      response = Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https',
                                                     open_timeout: 15, read_timeout: 120) do |http|
        http.request(request)
      end
      body = begin
        JSON.parse(response.body.to_s)
      rescue JSON::ParserError
        {}
      end
      return [true, body['project'] || {}] if response.code.to_i == 201
      detail = body['detail'].is_a?(String) ? body['detail'] : "The server answered #{response.code}."
      detail = 'The API key was not accepted. Check it under CutList connection.' if response.code.to_i == 401
      return [false, detail]
    end
  rescue StandardError => e
    [false, "Could not reach #{server} (#{e.class}: #{e.message})."]
  end

  def menu_action_send
    return unless (!server_url.empty? && !api_key.empty?) || menu_action_settings
    model = Sketchup.active_model
    name = model.title.to_s.empty? ? 'SketchUp model' : model.title
    obj_path = File.join(Dir.tmpdir, "cutlist_#{Time.now.to_i}.obj")
    export_to_obj(obj_path)
    ok, result = upload_project(obj_path, name, server_url, api_key)
    File.delete(obj_path) if File.exist?(obj_path)
    if ok
      UI.messagebox("Sent \"#{name}\" to CutList. Your browser will open so you can check the parts.")
      UI.openURL(server_url)
    else
      UI.messagebox("Could not send to CutList.\n\n#{result}")
    end
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
    menu.add_item('Send to CutList')                      { menu_action_send }
    menu.add_item('CutList connection...')                { menu_action_settings }
    menu.add_separator
    menu.add_item('Export selection to OBJ for cutlist') { menu_action_export }
    menu.add_item('Export and run cutlist-engine')        { menu_action_export_and_run }
    file_loaded(__FILE__)
  end
end
