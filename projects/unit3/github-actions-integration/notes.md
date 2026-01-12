
### Issues

- The working directory is not correctly being applied in some cases. This should have been fixed by requiring `working_directory` when calling `analyze_file_changes`.
  - Keep in mind that while I don't have the ability to specify cwd when testing, AI Agents may be able to specify their cwd.
  - extracted helper for fetching the cwd from `working_directory`.
  - **Currently defaulting to MCP server's directory**

### Timeline
- webhook_server.py is provided but how is it connected to github?
  - Do I need to add the webhook config to github? If so, I will need to use the smee forwarder since github webhooks cannot post to localhost.

  - Run webhook forwarder:
  
  `smee --url https://smee.io/Da0Z5Rjsn51r6IU --path /webhook/github --port 8080`

## Webhook Event Flow

1. Create and start smee proxy to forward Github events to local server. 
    - This is required because Github does not allow posting to localhost.
    - The cmd to start the proxy has a `--path` option to define the route handler path smee will forward the github event.

2. Create and start the local server that handles the github events forwarded by smee.
    - The event handler function triggers on requests directed to `localhost:<port>/webhook/github`.

3. Add the generated proxy url from smee to the desired git repo. 
    - This can also be enabled at an org-level.
    - Configure the desired events to send.
    - Once all 3 components are activated, github events will be forwarded to the proxy, forwarded to local server, and gha action runs written to file.

      <img src="image.png" alt="add proxy url to github webhook" width="300" />