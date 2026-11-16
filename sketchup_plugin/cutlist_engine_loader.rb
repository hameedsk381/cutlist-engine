# Cutlist Engine - SketchUp plugin loader
# ----------------------------------------
# Drop this file into your SketchUp Plugins folder, e.g.:
#   Windows: %AppData%/SketchUp/SketchUp 2024/SketchUp/Plugins/
#   macOS:   ~/Library/Application Support/SketchUp 2024/SketchUp/Plugins/
#
# It adds a "Cutlist Engine" menu under Extensions:
#   - Check and send to CutList: reads each board's real size from SketchUp,
#     shows what it found and what to fix, then sends it to a CutList server.
#   - Send to CutList (as a mesh): uploads an OBJ of the model instead.
#   - Export to OBJ / run the cutlist-engine CLI offline.
#
# Only the check and send actions call a server, and only the one you set under
# "CutList connection...". The export actions stay on this computer.

require 'sketchup.rb'
require 'extensions.rb'
require 'net/http'
require 'uri'
require 'json'
require 'tmpdir'

module CutlistEngine
  PLUGIN_NAME    = 'Cutlist Engine'.freeze
  PLUGIN_VERSION = '1.2.0'.freeze
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
  # Direct reader: sizes come from SketchUp itself, not from an exported mesh
  # ---------------------------------------------------------------------------
  #
  # Each group or component that has faces of its own becomes one "part". Its
  # size is the box of those faces in the part's OWN axes (so a rotated board
  # still reads length x width x thickness), scaled by the accumulated
  # transformation and converted from inches to millimetres. The server judges
  # the parts; this code only measures and sends.

  MM_PER_INCH = 25.4

  def instance?(entity)
    entity.is_a?(Sketchup::Group) || entity.is_a?(Sketchup::ComponentInstance)
  end

  def instance_definition(entity)
    return entity.definition if entity.respond_to?(:definition)
    entity.entities.parent
  end

  def hidden?(entity)
    return true if entity.respond_to?(:visible?) && !entity.visible?
    layer = entity.respond_to?(:layer) ? entity.layer : nil
    !layer.nil? && layer.respond_to?(:visible?) && !layer.visible?
  end

  # Returns [[a, b, c] in mm, fill] for the faces, or nil when they have no volume.
  # fill is how much of the part's box its two broad faces cover: 1.0 for a plain
  # rectangular board, less for notches, holes or curves.
  def measure_faces(faces, transform)
    box = Geom::BoundingBox.new
    faces.each { |face| box.add(face.bounds) }
    extents = [box.width, box.height, box.depth]
    scales = [transform.xscale.abs, transform.yscale.abs, transform.zscale.abs]
    dims = extents.each_with_index.map { |extent, i| extent * scales[i] * MM_PER_INCH }
    return nil if dims.count { |d| d <= 0.0 } > 1 # a line or a point, not a surface

    thin = extents.each_with_index.min_by { |extent, _| extent }[1]
    axis = [Geom::Vector3d.new(1, 0, 0), Geom::Vector3d.new(0, 1, 0), Geom::Vector3d.new(0, 0, 1)][thin]
    broad = faces.select { |face| face.normal.parallel?(axis) }.map(&:area).sort.reverse.first(2)
    plane = extents.each_with_index.reject { |_, i| i == thin }.map { |extent, _| extent }.inject(:*)
    fill = nil
    if !broad.empty? && plane && plane > 0.0
      fill = [(broad.inject(:+) / broad.length) / plane, 1.0].min.round(3)
    end
    [dims.map { |d| d.round(3) }, fill]
  end

  def material_name(entity, faces)
    material = entity.material
    material ||= faces.map(&:material).compact.first
    material ? material.display_name.to_s : ''
  end

  def collect_parts(entities, transform, path, parent_hidden, sink)
    entities.each do |entity|
      next unless instance?(entity)
      world = transform * entity.transformation
      definition = instance_definition(entity)
      name = entity.respond_to?(:name) ? entity.name.to_s.strip : ''
      hidden = parent_hidden || hidden?(entity)
      here = path + [name.empty? ? definition.name.to_s : name]
      children = definition.entities
      faces = children.grep(Sketchup::Face)
      unless faces.empty?
        measured = measure_faces(faces, world)
        if measured
          layer = entity.respond_to?(:layer) ? entity.layer : nil
          sink << {
            name: name,
            definition: definition.name.to_s,
            path: here.join(' > '),
            tag: layer ? layer.name.to_s : '',
            material: material_name(entity, faces),
            dims: measured[0],
            fill: measured[1],
            hidden: hidden
          }
        end
      end
      collect_parts(children, world, here, hidden, sink)
    end
  end

  # The selection if there is one, otherwise the whole model.
  def read_parts
    model = Sketchup.active_model
    source = model.selection.empty? ? model.entities : model.selection
    parts = []
    collect_parts(source, Geom::Transformation.new, [], false, parts)
    parts
  end

  def model_name
    title = Sketchup.active_model.title.to_s
    title.empty? ? 'SketchUp model' : title
  end

  # POST a JSON body with the API key. Returns [status_code, parsed_body_hash].
  def post_json(path, body)
    uri = URI.parse("#{server_url}#{path}")
    request = Net::HTTP::Post.new(uri)
    request['Authorization'] = "Bearer #{api_key}"
    request['Content-Type'] = 'application/json'
    request.body = JSON.generate(body)
    response = Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https',
                                                   open_timeout: 15, read_timeout: 120) do |http|
      http.request(request)
    end
    parsed = begin
      JSON.parse(response.body.to_s)
    rescue JSON::ParserError
      {}
    end
    [response.code.to_i, parsed]
  rescue StandardError => e
    [0, { 'detail' => "Could not reach #{server_url} (#{e.class}: #{e.message})." }]
  end

  def explain_failure(status, body)
    return 'The API key was not accepted. Check it under CutList connection.' if status == 401
    body['detail'].is_a?(String) ? body['detail'] : "The server answered #{status}."
  end

  def send_parts(payload)
    status, body = post_json('/api/projects/skp', payload.merge(name: model_name))
    if status == 201
      UI.messagebox("Sent \"#{model_name}\" to CutList. Your browser will open so you can see the plan.")
      UI.openURL(server_url)
    else
      UI.messagebox("Could not send to CutList.\n\n#{explain_failure(status, body)}")
    end
  end

  # Read the model, let the server judge it, show the result, then send on request.
  def menu_action_check_and_send
    return unless (!server_url.empty? && !api_key.empty?) || menu_action_settings

    parts = read_parts
    if parts.empty?
      UI.messagebox("No groups or components were found.\n\nSelect the furniture, or make each board " \
                    "its own group or component, then try again.")
      return
    end
    payload = { model: model_name, version: 1, parts: parts }
    status, body = post_json('/api/tools/skp/check', payload.merge(interactive: true))
    unless status == 200 && body['html'].is_a?(String)
      UI.messagebox("Could not check the model.\n\n#{explain_failure(status, body)}")
      return
    end

    @check_dialog.close if @check_dialog
    @check_dialog = UI::HtmlDialog.new(
      dialog_title: 'CutList check', width: 780, height: 680, resizable: true,
      style: UI::HtmlDialog::STYLE_DIALOG
    )
    @check_dialog.add_action_callback('send_to_cutlist') do |_context|
      @check_dialog.close
      send_parts(payload)
    end
    @check_dialog.add_action_callback('close_dialog') { |_context| @check_dialog.close }
    @check_dialog.set_html(body['html'])
    @check_dialog.show
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
    menu.add_item('Check and send to CutList')            { menu_action_check_and_send }
    menu.add_item('Send to CutList (as a mesh)')          { menu_action_send }
    menu.add_item('CutList connection...')                { menu_action_settings }
    menu.add_separator
    menu.add_item('Export selection to OBJ for cutlist') { menu_action_export }
    menu.add_item('Export and run cutlist-engine')        { menu_action_export_and_run }
    file_loaded(__FILE__)
  end
end
