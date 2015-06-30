#!/bin/python

import collections
import json
import os
import requests

# NOTE(pawelb): you can get list of issues in JSON format by entering
# https://zpaslab.atlassian.net/rest/api/2/search after browser login

# jira strings
jira_user = None
jira_password = None

# gitlab settings
gitlab_project_id = 1
gitlab_token = None


Issue = collections.namedtuple('Issue',
    ['project_id', 'title', 'description', 'assignee_id', 'milestone_id', 'labels', 'notes'])


# Fetches list of issues and for every issue, its comments (one file in jira_issues/* directory per issue)
# In case issues fie or files for particular issue is found on disk, no API call is made.
def fetch_jira_issues_json():
    jira_json = 'jira_issues.json'
    if not os.path.exists(jira_json):
        # reads jira issues from attlasiant server and dump to a file
        print 'opening jira page to get issues'
        r = requests.get('https://zpaslab.atlassian.net/rest/api/2/search',
                         auth=(jira_user, jira_password),
                         params={'maxResults': 150})
        if r.status_code != 200:
            print "invalid status code: ", r.status_code
            raise
        items_json = json.loads(r.text)
        f = open(jira_json, 'w')
        f.write(json.dumps(items_json, indent=4, separators=(',', ': ')))
        f.close()
    print 'opening jira json from file'
    f = open(jira_json).read()
    items = json.loads(f)

    # Now, read comments for every issue
    full_items = {"issues": []}
    jira_issues_dir = 'jira_issues'
    if not os.path.exists(jira_issues_dir):
        os.makedirs(jira_issues_dir)
    for i in items["issues"]:
        issue_file = os.path.join(jira_issues_dir, i["key"])
        if not os.path.exists(issue_file):
            print 'opening jira page to get details: %s' % i["key"]
            r = requests.get('https://zpaslab.atlassian.net/rest/api/2/issue/%s' % i["key"],
                             auth=(jira_user, jira_password))
            if r.status_code != 200:
                print "invalid status code: ", r.status_code
                raise
            item_json = json.loads(r.text)
            f = open(issue_file, 'w')
            f.write(json.dumps(item_json, indent=4, separators=(',', ': ')))
            f.close()
            full_items["issues"].append(item_json)
        else:
            f = open(issue_file)
            item_json = json.load(f)
            full_items["issues"].append(item_json)

    return full_items


# Restructures item list from jira and pushes them as gitlab issues.
# NOTE(pawelb): notes are pushed with api caller as authoer. To 'fix' this a little, we prepend the original author
# at the beginning of each note.
def push_issues_to_gitlab(items):
    issues = []
    for i in items["issues"]:
        project_id = gitlab_project_id
        title = i["fields"]["summary"]
        if i["fields"]["description"] is not None:
            description = i["fields"]["description"]
        else:
            description = ''
        assignee_id = None
        milestone_id = None
        labels = i["fields"]["labels"]
        priority_label = "priority-" + i["fields"]["priority"]["name"].lower()
        labels.append(priority_label)
        type_label = i["fields"]["issuetype"]["name"].lower()
        labels.append(type_label)
        notes = []
        if i["fields"]["comment"]["total"] > 0:
            for c in i["fields"]["comment"]["comments"]:
                note = c["author"]["displayName"] + ":\n\n" + c["body"]
                notes.append(note)

        new_issue = Issue(project_id, title, description, assignee_id, milestone_id, labels, notes)
        issues.append(new_issue)

    for issue in issues:
        push_issue_to_gitlab(issue)
    print 'Total issues: ', len(issues)

# For debugging: prints the issues in a human-readable form
def format_issue(issue):
    ret = []
    ret.append(issue.title + " (" + str(issue.project_id) + ")")
    ret.append('\tassignee_id: ' + str(issue.assignee_id))
    ret.append('\tmilestone_id: ' + str(issue.milestone_id))
    ret.append('\tlabels: ' + u', '.join(issue.labels))
    ret.append('\tdescription: ' + issue.description[0:50].replace('\n', '\t') + " [...]")
    ret.append('\tnotes: ' + u'\n'.join(x[:] for x in issue.notes))
    return u'\n'.join(ret).encode('utf-8').strip()

def push_issue_to_gitlab(issue):
    print '-------------------------------------------------------------'
    #print format_issue(issue)
    print
    gitlab_labels = ','.join(issue.labels)
    gitlab_issue = Issue(
        issue.project_id, issue.title, issue.description, issue.assignee_id,
        issue.milestone_id, gitlab_labels, None)

    issue_payload = json.dumps(gitlab_issue._asdict(), indent=4, separators=(',', ': '))
    issue_payload = gitlab_issue._asdict()
    headers = {'PRIVATE-TOKEN': gitlab_token}
    # print 'http://zpasomat:1234/api/v3/projects/%d/issues' % gitlab_project_id
    r = requests.post('http://zpasomat:1234/api/v3/projects/%d/issues' % gitlab_project_id,
                     headers=headers,
                     data=issue_payload)
    if r.status_code != 200 and r.status_code != 201:
        print r.status_code
        print r.text
        raise

    issue_id = r.json()["id"]
    for note in issue.notes:
        note_payload = {
            "id": gitlab_project_id,
            "issue_id": issue_id,
            "body": note
        }
        r = requests.post('http://zpasomat:1234/api/v3/projects/%d/issues/%d/notes' % (gitlab_project_id, issue_id),
                          headers=headers,
                          data=note_payload)
        if r.status_code != 200 and r.status_code != 201:
            print r.status_code
            print r.text
            raise


jira_items = fetch_jira_issues_json()
#print json.dumps(jira_items, indent=4, separators=(',', ': '))
push_issues_to_gitlab(jira_items)